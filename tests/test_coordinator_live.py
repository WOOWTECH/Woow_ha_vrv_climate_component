"""Live tests against the bench gateway 192.168.2.20."""
from __future__ import annotations

import pytest
from pymodbus.client import AsyncModbusTcpClient

from custom_components.zhijingling_vrv.coordinator import ZhijinglingCoordinator

GATEWAY = "192.168.2.20"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_gateway_read(hass):
    client = AsyncModbusTcpClient(GATEWAY, port=502, timeout=5)
    assert await client.connect()
    try:
        coord = ZhijinglingCoordinator(hass, client=client, slave_id=1, entry_id="live")
        data = await coord._async_update_data()
        # Simulator gateway reports idu_total = 64
        assert 1 <= data.gateway.idu_total <= 64
        # It should return at least one online IDU
        assert len(data.idus) >= 1
    finally:
        client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_gateway_write_roundtrip(hass):
    client = AsyncModbusTcpClient(GATEWAY, port=502, timeout=5)
    assert await client.connect()
    try:
        coord = ZhijinglingCoordinator(hass, client=client, slave_id=1, entry_id="live")
        await coord.async_refresh()
        # Toggle IDU 0 setpoint 22 → 23 → back to original
        original = coord.data.idus[0].set_temp
        try:
            await coord.async_write_idu(0, set_temp=23)
            await coord.async_refresh()
            assert coord.data.idus[0].set_temp == 23
        finally:
            # Always restore, even if the assertion above fails, so we do
            # not leave the bench gateway in a modified state.
            await coord.async_write_idu(0, set_temp=original)
    finally:
        client.close()
