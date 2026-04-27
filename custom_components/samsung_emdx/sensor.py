"""Sensors for the Samsung E-Paper integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_MANUFACTURER, DOMAIN, LOGGER
from .coordinator import SamsungEMDXDataUpdateCoordinator
from .entity import SamsungEMDXEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up device state entities."""
    coordinator = entry.runtime_data

    async_add_entities(
        [
            SamsungEMDXBatterySensor(coordinator),
        ]
    )


class SamsungEMDXBatterySensor(SamsungEMDXEntity, SensorEntity):
    """Representation of a Samsung E-Paper device's battery."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(self, coordinator: SamsungEMDXDataUpdateCoordinator) -> None:
        """Initialize with API object, device id."""
        super().__init__(coordinator=coordinator)
        self.hass = coordinator.hass
        serial_number = str(coordinator.config_entry.unique_id)
        self._serial_number = serial_number
        self._attr_unique_id = f"{serial_number}-battery"
        LOGGER.debug(
            f"Registering battery sensor {self._attr_unique_id}; device: {self._attr_device_info}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return basic device metadata."""
        return DeviceInfo(
            manufacturer=CONF_MANUFACTURER,
            identifiers={(DOMAIN, str(self._serial_number))},
            name=str(self.name),
        )

    @property
    def native_unit_of_measurement(self) -> str:
        """Specifies the native unit of measurement."""
        return "%"

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        await self.async_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.battery_percent is not None:
            self._attr_native_value = self.coordinator.battery_percent
        self._async_write_ha_state()
