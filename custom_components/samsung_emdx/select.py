"""Select platform for Samsung E-Paper integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SamsungEMDXConfigEntry
from .const import CONF_MANUFACTURER, DOMAIN, Orientation
from .entity import SamsungEMDXDataUpdateCoordinator, SamsungEMDXEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SamsungEMDXConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Samsung E-Paper select platform from a config entry."""

    coordinator = entry.runtime_data
    async_add_entities([SamsungEMDXOrientationSelectEntity(coordinator)])


class SamsungEMDXOrientationSelectEntity(SamsungEMDXEntity, SelectEntity):
    """Select entity for current charge."""

    _attr_has_entity_name = True
    _attr_options = [
        Orientation.LANDSCAPE,
        Orientation.PORTRAIT,
    ]

    def __init__(self, coordinator: SamsungEMDXDataUpdateCoordinator) -> None:
        """Initialize with API object, device id."""
        super().__init__(coordinator=coordinator)
        self.hass = coordinator.hass
        serial_number = str(coordinator.config_entry.unique_id)
        self._serial_number = serial_number
        self._attr_unique_id = f"{serial_number}-orientation"
        self._attr_name = "Orientation"

    @property
    def device_info(self) -> DeviceInfo:
        """Return basic device metadata."""
        return DeviceInfo(
            manufacturer=CONF_MANUFACTURER,
            identifiers={(DOMAIN, str(self._serial_number))},
            name=str(self.name),
        )

    @property
    def _value(self) -> Any:
        """Return value from coordinator data."""
        return self.coordinator.orientation

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return str(self._value)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.coordinator.set_orientation(option)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
