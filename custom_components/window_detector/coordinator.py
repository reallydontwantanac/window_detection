"""Coordinator for Window Detector — owns the dual-score state machine."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLOSE_DECAY,
    CONF_CLOSE_THRESHOLD,
    CONF_EQUILIBRIUM_DELTA,
    CONF_EQUILIBRIUM_SUPPRESS,
    CONF_OPEN_DECAY,
    CONF_OPEN_THRESHOLD,
    CONF_OUTDOOR_TEMP,
    CONF_REFERENCE_TEMP,
    CONF_ROOM_TEMP,
    DEFAULT_CLOSE_DECAY,
    DEFAULT_CLOSE_THRESHOLD,
    DEFAULT_EQUILIBRIUM_DELTA,
    DEFAULT_EQUILIBRIUM_SUPPRESS,
    DEFAULT_OPEN_DECAY,
    DEFAULT_OPEN_THRESHOLD,
    DOMAIN,
    HISTORY_MINUTES,
    TC10_WINDOW_MINUTES,
    TC20_WINDOW_MINUTES,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def _get_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return the numeric temperature for an entity, or None if unavailable.

    Supports both:
      - Sensor entities whose state IS the temperature (e.g. ``sensor.foo_temp``)
      - Weather entities whose temperature is on ``.attributes.temperature``
        (e.g. ``weather.home``)
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", "none", ""):
        return None

    # First try the state itself (sensor entities)
    try:
        return float(state.state)
    except (ValueError, TypeError):
        pass

    # Fall back to the temperature attribute (weather entities)
    attr = state.attributes.get("temperature")
    if attr is None:
        return None
    try:
        return float(attr)
    except (ValueError, TypeError):
        return None


class WindowDetectorCoordinator(DataUpdateCoordinator):
    """Manages the dual-score state machine for one window sensor."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self._entry = entry

        # Persistent score state — survives between coordinator updates
        self._open_score: float = 0.0
        self._close_score: float = 0.0
        self._is_open: bool = False

        # Ring buffer: list of (timestamp, temp) for tc10/tc20 calculation
        self._temp_history: list[tuple[datetime, float]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def open_score(self) -> float:
        return round(self._open_score, 2)

    @property
    def close_score(self) -> float:
        return round(self._close_score, 2)

    # ------------------------------------------------------------------
    # Tuning params (from options, with defaults)
    # ------------------------------------------------------------------

    def _opt(self, key: str, default: float) -> float:
        return float(self._entry.options.get(key, default))

    @property
    def _open_thresh(self) -> float:
        return self._opt(CONF_OPEN_THRESHOLD, DEFAULT_OPEN_THRESHOLD)

    @property
    def _close_thresh(self) -> float:
        return self._opt(CONF_CLOSE_THRESHOLD, DEFAULT_CLOSE_THRESHOLD)

    @property
    def _open_decay(self) -> float:
        return self._opt(CONF_OPEN_DECAY, DEFAULT_OPEN_DECAY)

    @property
    def _close_decay(self) -> float:
        return self._opt(CONF_CLOSE_DECAY, DEFAULT_CLOSE_DECAY)

    @property
    def _eq_delta(self) -> float:
        return self._opt(CONF_EQUILIBRIUM_DELTA, DEFAULT_EQUILIBRIUM_DELTA)

    @property
    def _eq_suppress(self) -> int:
        return int(self._opt(CONF_EQUILIBRIUM_SUPPRESS, DEFAULT_EQUILIBRIUM_SUPPRESS))

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def _push_temp(self, temp: float) -> None:
        now = dt_util.utcnow()
        self._temp_history.append((now, temp))
        # Trim anything older than we need
        cutoff = now - timedelta(minutes=HISTORY_MINUTES)
        self._temp_history = [(t, v) for t, v in self._temp_history if t >= cutoff]

    def _temp_change(self, minutes: int) -> float | None:
        """Return (current_temp - temp_N_minutes_ago), or None if insufficient history.

        Requires at least one sample older than `minutes - 2` minutes so the result
        actually represents an N-minute change rather than a much shorter interval
        when history is still warming up after restart.
        """
        if len(self._temp_history) < 2:
            return None
        now = dt_util.utcnow()
        target = now - timedelta(minutes=minutes)
        min_age = timedelta(minutes=max(1, minutes - 2))
        candidates = [
            (abs((t - target).total_seconds()), v)
            for t, v in self._temp_history
            if (now - t) >= min_age
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        past_temp = candidates[0][1]
        current_temp = self._temp_history[-1][1]
        return current_temp - past_temp

    # ------------------------------------------------------------------
    # Evidence scoring
    # ------------------------------------------------------------------

    def _score_evidence(
        self,
        deriv: float | None,
        tc10: float | None,
        tc20: float | None,
        delta_out: float | None,
    ) -> tuple[int, int]:
        """Return (open_evidence, close_evidence) for this tick."""
        oe = 0
        ce = 0

        # Derivative: fast signal for detecting the opening event
        if deriv is not None:
            if deriv < -0.15:
                oe += 3
            elif deriv < -0.08:
                oe += 1
            if deriv > 0.12:
                ce += 3
            elif deriv > 0.06:
                ce += 1

        # 10-minute cumulative change: primary sustained signal
        if tc10 is not None:
            if tc10 < -0.35:
                oe += 4
            elif tc10 < -0.15:
                oe += 2
            elif tc10 < -0.05:
                oe += 1
            if tc10 > 0.30:
                ce += 4
            elif tc10 > 0.15:
                ce += 2
            elif tc10 > 0.05:
                ce += 1

        # 20-minute cumulative change: corroboration
        if tc20 is not None:
            if tc20 < -0.5:
                oe += 2
            elif tc20 < -0.2:
                oe += 1
            if tc20 > 0.4:
                ce += 2
            elif tc20 > 0.2:
                ce += 1

        # Equilibrium suppression: when open and room has equilibrated near outdoor
        # temperature, the tc signals go flat — don't let that accumulate close evidence
        if self._is_open and delta_out is not None:
            if delta_out < self._eq_delta:
                ce = max(0, ce - self._eq_suppress)

        return oe, ce

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Called every UPDATE_INTERVAL_SECONDS by the coordinator."""
        room_id = self._entry.data[CONF_ROOM_TEMP]
        outdoor_id = self._entry.data[CONF_OUTDOOR_TEMP]
        ref_id = self._entry.data.get(CONF_REFERENCE_TEMP)

        t_room = _get_float(self.hass, room_id)
        t_out = _get_float(self.hass, outdoor_id)
        t_ref = _get_float(self.hass, ref_id)

        if t_room is None:
            # Can't do anything without a room reading — hold state
            _LOGGER.debug("Room temp unavailable, holding state")
            return self._state_dict()

        # Push to history for tc calculations
        self._push_temp(t_room)

        # Compute signals from history
        deriv = self._compute_deriv()

        tc10 = self._temp_change(TC10_WINDOW_MINUTES)
        tc20 = self._temp_change(TC20_WINDOW_MINUTES)

        delta_out = abs(t_room - t_out) if t_out is not None else None

        # Optional: reference sensor corroboration
        ref_oe = 0
        ref_ce = 0
        if t_ref is not None and delta_out is not None:
            delta_ref = abs(t_room - t_ref)
            if delta_ref > delta_out:
                ref_oe += 1  # closer to outdoor than to reference room → more open evidence
            elif delta_out > 0 and delta_ref < delta_out * 0.6:
                ref_ce += 1  # much closer to reference room → more closed evidence

        oe, ce = self._score_evidence(deriv, tc10, tc20, delta_out)
        oe += ref_oe
        ce += ref_ce

        # Update scores with decay
        self._open_score = min(20.0, self._open_score * self._open_decay + oe)
        self._close_score = min(20.0, self._close_score * self._close_decay + ce)

        # State transitions with hysteresis
        if not self._is_open and self._open_score >= self._open_thresh:
            _LOGGER.info(
                "Window opened (open_score=%.1f >= %.1f)",
                self._open_score,
                self._open_thresh,
            )
            self._is_open = True
            self._close_score = 0.0  # reset opposing score on transition

        elif self._is_open and self._close_score >= self._close_thresh:
            _LOGGER.info(
                "Window closed (close_score=%.1f >= %.1f)",
                self._close_score,
                self._close_thresh,
            )
            self._is_open = False
            self._open_score = 0.0  # reset opposing score on transition

        _LOGGER.debug(
            "open=%s open_score=%.1f close_score=%.1f oe=%d ce=%d "
            "tc10=%s tc20=%s deriv=%s delta_out=%s",
            self._is_open,
            self._open_score,
            self._close_score,
            oe,
            ce,
            f"{tc10:.2f}" if tc10 is not None else "n/a",
            f"{tc20:.2f}" if tc20 is not None else "n/a",
            f"{deriv:.3f}" if deriv is not None else "n/a",
            f"{delta_out:.1f}" if delta_out is not None else "n/a",
        )

        return self._state_dict()

    def _compute_deriv(self) -> float | None:
        """Compute a smoothed derivative as a 5-min averaged temperature change (°C/min).

        A raw 1-minute difference is dominated by sensor noise (typical sensors
        have ±0.05°C jitter on every reading); empirically that produces dozens
        of false-cooling and false-warming evidence points per day during stable
        closed periods. A 5-minute averaged derivative cuts that noise to zero
        while staying responsive enough to catch a genuine window-opening event.
        Equivalent to: (current_temp - temp_5_min_ago) / 5.
        """
        tc5 = self._temp_change(5)
        if tc5 is None:
            return None
        return tc5 / 5.0

    def _state_dict(self) -> dict[str, Any]:
        return {
            "is_open": self._is_open,
            "open_score": round(self._open_score, 2),
            "close_score": round(self._close_score, 2),
        }
