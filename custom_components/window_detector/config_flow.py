"""Config flow for Window Detector."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

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
)

_LOGGER = logging.getLogger(__name__)


def _indoor_sensor_selector() -> selector.EntitySelector:
    """Indoor sensors must be temperature sensors only."""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )


def _outdoor_temp_selector() -> selector.EntitySelector:
    """Outdoor temperature can come from either a temperature sensor or a weather entity.

    Weather entities expose temperature on the ``temperature`` attribute rather
    than as their state, so the coordinator handles both transparently.
    """
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            multiple=False,
            filter=[
                {"domain": "sensor", "device_class": "temperature"},
                {"domain": "weather"},
            ],
        )
    )


class WindowDetectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Window Detector."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        errors: dict[str, str] = {}

        if user_input is not None:
            for key in (CONF_ROOM_TEMP, CONF_OUTDOOR_TEMP):
                if self.hass.states.get(user_input[key]) is None:
                    errors[key] = "entity_not_found"

            ref = user_input.get(CONF_REFERENCE_TEMP)
            if ref and self.hass.states.get(ref) is None:
                errors[CONF_REFERENCE_TEMP] = "entity_not_found"

            if not errors:
                # Use the room sensor as the unique identifier so the same
                # window cannot be configured twice.
                await self.async_set_unique_id(user_input[CONF_ROOM_TEMP])
                self._abort_if_unique_id_configured()

                room_state = self.hass.states.get(user_input[CONF_ROOM_TEMP])
                title = (
                    f"Window ({room_state.name})"
                    if room_state is not None
                    else "Window Detector"
                )
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_ROOM_TEMP): _indoor_sensor_selector(),
                vol.Required(CONF_OUTDOOR_TEMP): _outdoor_temp_selector(),
                vol.Optional(CONF_REFERENCE_TEMP): _indoor_sensor_selector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WindowDetectorOptionsFlow(config_entry)


class WindowDetectorOptionsFlow(OptionsFlow):
    """Handle options (tuning parameters)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_OPEN_THRESHOLD,
                    default=opts.get(CONF_OPEN_THRESHOLD, DEFAULT_OPEN_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=30, step=1, mode="slider")
                ),
                vol.Optional(
                    CONF_CLOSE_THRESHOLD,
                    default=opts.get(CONF_CLOSE_THRESHOLD, DEFAULT_CLOSE_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=5, max=30, step=1, mode="slider")
                ),
                vol.Optional(
                    CONF_OPEN_DECAY,
                    default=opts.get(CONF_OPEN_DECAY, DEFAULT_OPEN_DECAY),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.70, max=0.99, step=0.01, mode="slider"
                    )
                ),
                vol.Optional(
                    CONF_CLOSE_DECAY,
                    default=opts.get(CONF_CLOSE_DECAY, DEFAULT_CLOSE_DECAY),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.70, max=0.99, step=0.01, mode="slider"
                    )
                ),
                vol.Optional(
                    CONF_EQUILIBRIUM_DELTA,
                    default=opts.get(CONF_EQUILIBRIUM_DELTA, DEFAULT_EQUILIBRIUM_DELTA),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0, max=15.0, step=0.5, mode="slider"
                    )
                ),
                vol.Optional(
                    CONF_EQUILIBRIUM_SUPPRESS,
                    default=opts.get(
                        CONF_EQUILIBRIUM_SUPPRESS, DEFAULT_EQUILIBRIUM_SUPPRESS
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=5, step=1, mode="slider")
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
