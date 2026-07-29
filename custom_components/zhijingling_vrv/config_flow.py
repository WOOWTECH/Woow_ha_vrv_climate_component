"""Config flow for ZhiJingLing VRV."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from pymodbus.client import AsyncModbusTcpClient

from .const import DEFAULT_PORT, DEFAULT_SLAVE_ID, DOMAIN, MAX_IDUS

CONF_SLAVE_ID = "slave_id"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): vol.All(int, vol.Range(min=1, max=247)),
    }
)


class CannotConnect(Exception):
    """Raised when TCP connect fails."""


class InvalidDevice(Exception):
    """Raised when the device does not look like a ZhiJingLing gateway."""


async def _validate(hass: HomeAssistant, host: str, port: int, slave_id: int) -> None:
    client = AsyncModbusTcpClient(host, port=port, timeout=5)
    try:
        if not await client.connect():
            raise CannotConnect
        resp = await client.read_holding_registers(2000, count=6, device_id=slave_id)
        if resp.isError():
            raise InvalidDevice
        _brand, _pt, idu_total, *_ = resp.registers
        if not 1 <= idu_total <= MAX_IDUS:
            raise InvalidDevice
    finally:
        client.close()


class ZhijinglingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()

            try:
                await _validate(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_SLAVE_ID],
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidDevice:
                errors["base"] = "invalid_device"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"智精靈閘道 ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
