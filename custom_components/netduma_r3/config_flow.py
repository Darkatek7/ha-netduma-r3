from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

class NetdumaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input["host"].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"Netduma R3 ({host})", data=user_input)

        schema = vol.Schema(
            {
                vol.Required("host"): str,  # e.g. 192.168.77.1
                vol.Optional("verify_ssl", default=False): bool,
                vol.Optional("username"): str,
                vol.Optional("password"): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
