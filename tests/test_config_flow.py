"""Config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.zhijingling_vrv.const import DOMAIN


class _Ok:
    registers = [10, 20, 32, 16, 30, 0]

    def isError(self):  # noqa: N802
        return False


class _Bad:
    registers = []

    def isError(self):  # noqa: N802
        return True


def _fake_client(*, connect_ok=True, resp=None):
    c = MagicMock()
    c.connect = AsyncMock(return_value=connect_ok)
    c.close = MagicMock()
    c.read_holding_registers = AsyncMock(return_value=resp or _Ok())
    return c


@pytest.mark.asyncio
async def test_user_flow_success(hass, enable_custom_integrations):
    with patch(
        "custom_components.zhijingling_vrv.config_flow.AsyncModbusTcpClient",
        return_value=_fake_client(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.2.20", CONF_PORT: 502, "slave_id": 1},
        )
        assert result2["type"] == "create_entry"
        assert result2["title"] == "智精靈閘道 (192.168.2.20)"


@pytest.mark.asyncio
async def test_user_flow_cannot_connect(hass, enable_custom_integrations):
    with patch(
        "custom_components.zhijingling_vrv.config_flow.AsyncModbusTcpClient",
        return_value=_fake_client(connect_ok=False),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 502, "slave_id": 1},
        )
        assert result2["type"] == "form"
        assert result2["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_user_flow_invalid_device(hass, enable_custom_integrations):
    with patch(
        "custom_components.zhijingling_vrv.config_flow.AsyncModbusTcpClient",
        return_value=_fake_client(resp=_Bad()),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.2.99", CONF_PORT: 502, "slave_id": 1},
        )
        assert result2["type"] == "form"
        assert result2["errors"] == {"base": "invalid_device"}
