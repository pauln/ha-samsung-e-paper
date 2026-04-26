"""The Samsung E-Paper integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .coordinator import SamsungEMDXConfigEntry, SamsungEMDXDataUpdateCoordinator
from .services import async_setup_services

_PLATFORMS: list[Platform] = [Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SamsungEMDXConfigEntry) -> bool:
    """Set up Samsung E-Paper from a config entry."""

    coordinator = SamsungEMDXDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Samsung E-Paper integration."""
    async_setup_services(hass)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SamsungEMDXConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
