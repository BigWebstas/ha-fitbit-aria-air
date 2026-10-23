"""Config flow for the Fitbit Aria Air."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .const import (
    CONF_ALWAYS_CONNECT,
    CONF_KEY,
    CONF_UNIT,
    DOMAIN,
    LOCAL_NAME,
    UNIT_KG,
    UNIT_LB,
)
from .decode import parse_key

UNIT_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[UNIT_KG, UNIT_LB],
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="unit",
    )
)


class AriaAirConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a scale found by Bluetooth, or picked from the list."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._address: str | None = None
        self._name: str | None = None
        self._discovered: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = discovery_info.name
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_key()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose among scales Home Assistant can see."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._name = self._discovered[self._address]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_key()

        configured = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.name == LOCAL_NAME and info.address not in configured:
                self._discovered[info.address] = f"{info.name} ({info.address})"

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered)}),
        )

    async def async_step_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the scale's key and the unit it reports in."""
        errors: dict[str, str] = {}
        default_unit = UNIT_LB if self.hass.config.units is US_CUSTOMARY_SYSTEM else UNIT_KG

        if user_input is not None:
            try:
                key = parse_key(user_input[CONF_KEY])
            except ValueError:
                errors[CONF_KEY] = "invalid_key"
            else:
                return self.async_create_entry(
                    title=f"Aria Air {self._address[-5:].replace(':', '')}",
                    data={
                        CONF_ADDRESS: self._address,
                        CONF_KEY: key.hex(),
                        CONF_UNIT: user_input[CONF_UNIT],
                    },
                )

        return self.async_show_form(
            step_id="key",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_UNIT, default=default_unit): UNIT_SELECTOR,
                }
            ),
            errors=errors,
            description_placeholders={"name": self._name or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return AriaAirOptionsFlow()


class AriaAirOptionsFlow(OptionsFlow):
    """Change the unit or the connection behaviour after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry = self.config_entry
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UNIT,
                        default=entry.options.get(CONF_UNIT, entry.data[CONF_UNIT]),
                    ): UNIT_SELECTOR,
                    vol.Required(
                        CONF_ALWAYS_CONNECT,
                        default=entry.options.get(CONF_ALWAYS_CONNECT, False),
                    ): bool,
                }
            ),
        )
