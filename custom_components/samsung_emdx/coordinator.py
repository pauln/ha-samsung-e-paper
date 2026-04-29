"""Coordinator for the Samsung E-Paper integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta
import hashlib
import socket
from typing import Any

from samsung_mdc import MDC, commands as MDCCommands
from samsung_mdc.exceptions import MDCError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER, LOW_POWER_WAKE_PORT, Orientation

type SamsungEMDXConfigEntry = ConfigEntry[SamsungEMDXDataUpdateCoordinator]

MDCOrientation = MDCCommands._COMMON.ORIENTATION_MODE_STATE


class SamsungEMDXDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for the SamsungEMDX integration."""

    config_entry: SamsungEMDXConfigEntry
    upload_task: asyncio.Task | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SamsungEMDXConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            update_interval=timedelta(days=1),
            name=DOMAIN,
        )

        self._low_power_ip: str | None = config_entry.data.get("lp_ip_address")
        self._low_power_mac: str | None = config_entry.data.get("lp_mac_address")
        self._ip_address: str | None = config_entry.data.get("ip_address")
        self._pin: str | None = config_entry.data.get("pin")
        self._display_id: int | None = config_entry.data.get("display_id")
        self._mdc_connection = None
        self._battery_percent = None
        self._orientation = None

        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, self.config_entry.unique_id)}
        )
        self._current_version = device_entry.sw_version

        self.is_on: bool | None = None
        self.async_extra_update: Callable[[], Coroutine[Any, Any, None]] | None = None

    async def _async_update_data(self) -> None:
        """Fetch data from Samsung E-Paper device."""
        await self.low_power_wake()
        if self.async_extra_update:
            await self.async_extra_update()

    async def low_power_wake(self) -> None:
        """Wake the device via its low-power wifi module."""
        if (
            self._low_power_mac is None
            or self._low_power_ip is None
            or self._pin is None
            or self._display_id is None
            or self._ip_address is None
        ):
            return

        magic_key = f"{self._low_power_mac.upper()}:E-Paper"
        wake_hash = hashlib.new("sha256")
        wake_hash.update(magic_key.encode())
        wake_msg = wake_hash.hexdigest()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        for i in range(1, 11):
            LOGGER.debug(f"Low-power wake attempt {i}/10")

            for j in range(1, 11):
                LOGGER.debug(f"Sending wake message {j}/10")
                encoded_msg = wake_msg.encode()
                sock.sendto(encoded_msg, (self._low_power_ip, LOW_POWER_WAKE_PORT))
                try:
                    wake_resp = sock.recv(len(wake_msg))
                    if wake_resp == encoded_msg:
                        # The LP chip returns the wake message as a response on successful wake
                        LOGGER.debug(
                            "Wake successful; waiting for device to come online"
                        )
                        break

                    # Empty or incorrect wake response; try again after a brief pause.
                    await asyncio.sleep(0.2)
                except TimeoutError:
                    pass

            await asyncio.sleep(3)

            for j in range(1, 6):
                LOGGER.debug(f"MDC connection attempt {j}/5")
                try:
                    async with MDC(self._ip_address, pin=self._pin) as mdc:
                        (
                            battery_percent,
                            power_source,
                            warning_enabled,
                        ) = await mdc.battery_status(self._display_id)
                        LOGGER.debug(
                            f"Battery: {battery_percent}%; power source: {power_source}, warning: {warning_enabled}"
                        )
                        sock.close()
                        self._battery_percent = battery_percent
                        self._mdc_connection = mdc
                        # Check configured device orientation.
                        await self.get_orientation()
                        # Check current firmware version.
                        await self.get_firmware_version()
                        # Notify sensor entities of updated data.
                        self.async_update_listeners()
                        return
                except MDCError, OSError:
                    pass

                await asyncio.sleep(2)
        sock.close()
        self._mdc_connection = None
        return

    async def set_content_download(self, url: str) -> None:
        """Sends a content URL to the device."""
        await self._mdc_connection.set_content_download(self._display_id, [url])

    async def get_orientation(self) -> Orientation | None:
        """Gets the device's configured orientation."""
        orientation = await self._mdc_connection.osd_menu_orientation(self._display_id)
        self._orientation = mdc_orientation_to_hass_orientation(orientation[0])

        LOGGER.debug(f"Reported orientation: {self._orientation} ({orientation[0]})")

        # Notify sensor entities of updated data.
        self.async_update_listeners()

        return self._orientation

    async def get_firmware_version(self) -> str:
        """Gets the device's current firmware version."""
        firmware_version = await self._mdc_connection.software_version(self._display_id)

        if firmware_version[0] != self._current_version:
            device_registry = dr.async_get(self.hass)
            device_entry = device_registry.async_get_device(
                identifiers={(DOMAIN, self.config_entry.unique_id)}
            )
            assert device_entry
            device_registry.async_update_device(
                device_entry.id,
                sw_version=firmware_version[0],
            )
            self._current_version = firmware_version[0]

        LOGGER.debug(f"Current firmware version: {self._current_version}")

        return self._current_version

    @property
    def battery_percent(self) -> int | None:
        """Battery charge percentage."""
        return self._battery_percent

    @property
    def orientation(self) -> str | None:
        """Physical orientation of the device."""
        return self._orientation

    async def set_orientation(self, orientation: str) -> Orientation | None:
        """Sets the physical orientation of the device."""
        await self.low_power_wake()

        mdc_orientation = hass_orientation_to_mdc_orientation(orientation)
        new_orientation = await self._mdc_connection.osd_menu_orientation(
            self._display_id, [mdc_orientation]
        )
        self._orientation = mdc_orientation_to_hass_orientation(new_orientation[0])

        LOGGER.debug(
            f"Reported orientation: {self._orientation} ({new_orientation[0]})"
        )

        # Notify sensor entities of updated data.
        self.async_update_listeners()

        return self._orientation


def mdc_orientation_to_hass_orientation(mdc_orientation: MDCOrientation) -> Orientation:
    "Converts an MDC Orientation enum to the local equivalent."
    if mdc_orientation == MDCOrientation.PORTRAIT_270:
        return Orientation.PORTRAIT
    return Orientation.LANDSCAPE


def hass_orientation_to_mdc_orientation(orientation: str) -> MDCOrientation:
    "Converts a local Orientation enum to the MDC equivalent."
    if orientation == Orientation.PORTRAIT:
        return MDCOrientation.PORTRAIT_270
    return MDCOrientation.LANDSCAPE_0
