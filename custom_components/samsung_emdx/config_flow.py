"""Config flow for the Samsung E-Paper integration."""

from __future__ import annotations

import contextlib
import ipaddress
from typing import Any

from samsung_mdc import MDC
from samsung_mdc.connection import MDCConnection
from samsung_mdc.exceptions import MDCError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_IP_ADDRESS, CONF_PIN
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DOMAIN, LOGGER


class SamsungEpaperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Samsung E-Paper integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._name = "Samsung E-Paper"
        self._display_id = 0
        self._ip_address = None
        self._lp_ip_address = None
        self._lp_mac_address = None
        self._pin = None
        self._serial_number = None

    def get_config(self):
        """Returns a dict of user-provided and generated config."""
        return {
            "name": self._name,
            "display_id": self._display_id,
            "ip_address": self._ip_address,
            "lp_ip_address": self._lp_ip_address,
            "lp_mac_address": self._lp_mac_address,
            "pin": self._pin,
            "serial_number": self._serial_number,
        }

    async def get_low_power_config(self, conn: MDCConnection) -> MDCError | None:
        """Retrieves low-power networking config via MDC."""
        try:
            LOGGER.debug("Attempting to retrieve low-power network config via MDC")
            lp_resp = await conn.low_power_networking(self._display_id)
            self._lp_ip_address = lp_resp[0]
            self._lp_mac_address = lp_resp[1]
        except MDCError as e:
            return e
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Process user-provided config to set up integration."""
        errors = {}
        if user_input is not None:
            if user_input[CONF_IP_ADDRESS] != "":
                self._ip_address = user_input[CONF_IP_ADDRESS]

            if user_input[CONF_PIN] != "":
                self._pin = user_input[CONF_PIN]

            with contextlib.suppress(ZeroDivisionError):
                ip_address = ipaddress.ip_address(user_input[CONF_IP_ADDRESS])

            if ip_address is not None and self._pin is not None:
                try:
                    LOGGER.debug("Attempting to connect via MDC")
                    async with MDC(
                        self._ip_address, pin=self._pin
                    ) as mdc:  # , verbose=True
                        serial_resp = await mdc.serial_number(self._display_id)
                        self._serial_number = serial_resp[0]
                        await self.async_set_unique_id(self._serial_number)
                        self._abort_if_unique_id_configured(
                            {CONF_HOST: self._serial_number}
                        )

                        name_resp = await mdc.device_name(self._display_id)
                        self._name = name_resp[0]

                        lp_err = await self.get_low_power_config(mdc)
                        if lp_err is not None:
                            raise lp_err

                        return self.async_create_entry(
                            title=self._name,
                            data=self.get_config(),
                        )
                except MDCError:
                    errors["base"] = "mdc_connection_failed"

            errors["base"] = "invalid_ip"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IP_ADDRESS,
                    ): str,
                    vol.Required(
                        CONF_PIN,
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_ssdp(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle SSDP discover."""
        self._ip_address = discovery_info.ssdp_headers["_host"]
        self._name = discovery_info.upnp["friendlyName"]
        self._serial_number = discovery_info.upnp["serialNumber"]

        await self.async_set_unique_id(self._serial_number)
        self._abort_if_unique_id_configured({CONF_HOST: self._serial_number})

        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-confirmation of discovered node."""
        errors = {}
        if user_input is not None:
            self._pin = user_input[CONF_PIN]

            try:
                LOGGER.debug("Attempting to connect via MDC")
                async with MDC(
                    self._ip_address, pin=self._pin
                ) as mdc:  # , verbose=True
                    lp_err = await self.get_low_power_config(mdc)
                    if lp_err is not None:
                        raise lp_err

                return self.async_create_entry(
                    title=self._name,
                    data=self.get_config(),
                )
            except MDCError:
                errors["base"] = "mdc_connection_failed"

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": self._name},
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IP_ADDRESS,
                        default=self._ip_address,
                    ): str,
                    vol.Required(
                        CONF_PIN,
                    ): str,
                }
            ),
            errors=errors,
        )
