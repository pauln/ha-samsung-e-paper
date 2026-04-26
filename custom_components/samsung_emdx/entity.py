"""Base Samsung E-Paper Entity."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MANUFACTURER, DOMAIN, LOGGER
from .coordinator import SamsungEMDXDataUpdateCoordinator


class SamsungEMDXEntity(CoordinatorEntity[SamsungEMDXDataUpdateCoordinator], Entity):
    """Defines a base Samsung E-Paper entity."""

    _attr_has_entity_name = True

    def __init__(self, *, coordinator: SamsungEMDXDataUpdateCoordinator) -> None:
        """Initialize the Samsung E-Paper entity."""
        super().__init__(coordinator)
        config_entry = coordinator.config_entry
        self._low_power_ip: str | None = config_entry.data.get("lp_ip_address")
        self._low_power_mac: str | None = config_entry.data.get("lp_mac_address")
        self._ip_address: str | None = config_entry.data.get("ip_address")
        self._pin: str | None = config_entry.data.get("pin")
        self._display_id: int | None = config_entry.data.get("display_id")
        self._mdc_connection = None
        self._battery_percent = None
        # Fallback for legacy models that doesn't have a API to retrieve MAC or SerialNumber
        self._attr_unique_id = config_entry.unique_id or config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            manufacturer=CONF_MANUFACTURER,
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=config_entry.data.get("name"),
        )
        LOGGER.debug(
            f"Registering entity {self._attr_unique_id}; device: {self._attr_device_info}"
        )

    @property
    def available(self) -> bool:
        """Return the availability of the device."""
        if not super().available:  # or self._bridge.auth_failed:
            return False
        # TODO: figure out how to determine if low-power wifi device is available.
        return True

    @property
    def device_info(self) -> DeviceInfo:
        """Return basic device metadata."""
        return DeviceInfo(
            manufacturer=CONF_MANUFACTURER,
            identifiers={(DOMAIN, str(self._attr_unique_id))},
            name=str(self.name),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self.coordinator.async_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on via low-power wake."""
        await self.coordinator.low_power_wake()

    @property
    def battery_percent(self) -> int | None:
        """Battery charge percentage."""
        return self.coordinator.battery_percent

    @property
    def orientation(self) -> str | None:
        """Physical orientation of the device."""
        return self.coordinator.orientation
