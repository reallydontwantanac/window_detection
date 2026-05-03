"""Binary sensor for Window Detector."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OUTDOOR_TEMP,
    CONF_REFERENCE_TEMP,
    CONF_ROOM_TEMP,
    DOMAIN,
)
from .coordinator import WindowDetectorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Window Detector binary sensor from a config entry."""
    coordinator: WindowDetectorCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WindowBinarySensor(coordinator, entry)])


class WindowBinarySensor(CoordinatorEntity[WindowDetectorCoordinator], BinarySensorEntity):
    """Binary sensor representing a single window's open/closed state."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW
    _attr_has_entity_name = True
    _attr_name = None  # use device name as entity name

    def __init__(
        self,
        coordinator: WindowDetectorCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_window"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Window Detector",
            model="Temperature-based",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the window is open."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["is_open"]

    @property
    def extra_state_attributes(self) -> dict:
        """Expose scores and config as diagnostic attributes."""
        data = self.coordinator.data or {}
        entry = self._entry
        return {
            "open_score": data.get("open_score"),
            "close_score": data.get("close_score"),
            "room_temp_sensor": entry.data.get(CONF_ROOM_TEMP),
            "outdoor_temp_sensor": entry.data.get(CONF_OUTDOOR_TEMP),
            "reference_temp_sensor": entry.data.get(CONF_REFERENCE_TEMP),
        }
