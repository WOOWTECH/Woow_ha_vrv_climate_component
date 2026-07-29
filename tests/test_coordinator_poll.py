"""Coordinator polling — with a fake AsyncModbusTcpClient."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.zhijingling_vrv.coordinator import ZhijinglingCoordinator


class _RegResponse:
    def __init__(self, regs: list[int]):
        self.registers = regs

    def isError(self) -> bool:  # noqa: N802 — pymodbus API
        return False


class _ErrorResponse:
    registers: list[int] = []

    def isError(self) -> bool:  # noqa: N802
        return True


def _make_client(*, gateway_meta=None, idu_batches=None, write_ok=True):
    """Build a fake AsyncModbusTcpClient with scripted responses."""
    client = MagicMock()
    client.connect = AsyncMock(return_value=True)
    client.close = MagicMock()

    async def read_holding_registers(address, *, count, device_id):
        if address == 2000:
            return _RegResponse(gateway_meta or [1, 1, 2, 16, 30, 0])
        if idu_batches and address in idu_batches:
            return _RegResponse(idu_batches[address])
        return _RegResponse([0] * count)

    async def write_registers(address, values, *, device_id):
        return _RegResponse([]) if write_ok else _ErrorResponse()

    client.read_holding_registers = AsyncMock(side_effect=read_holding_registers)
    client.write_registers = AsyncMock(side_effect=write_registers)
    return client


@pytest.mark.asyncio
async def test_poll_returns_online_idus_only(hass):
    # IDU 0 online (room 25), IDU 1 offline (all zero)
    batches = {
        0: [1, 2, 22, 3, 25, 0] + [0] * (6 * 14),  # slot 0 online, rest offline
    }
    client = _make_client(idu_batches=batches)
    coord = ZhijinglingCoordinator(hass, client=client, slave_id=1, entry_id="e1")
    data = await coord._async_update_data()
    assert 0 in data.idus
    assert data.idus[0].room_temp == 25
    assert data.gateway.idu_total == 2


@pytest.mark.asyncio
async def test_poll_dispatches_new_idu_signal(hass):
    batches = {0: [1, 2, 22, 3, 25, 0] + [0] * (6 * 14)}
    client = _make_client(idu_batches=batches)
    coord = ZhijinglingCoordinator(hass, client=client, slave_id=1, entry_id="e1")

    signals = []

    def _fake_dispatch(hass_arg, signal, payload):
        signals.append((signal, payload))

    coord._dispatch = _fake_dispatch  # type: ignore[assignment]

    await coord._async_update_data()  # first poll → new IDUs
    assert signals and signals[0][1] == {0}

    await coord._async_update_data()  # second poll → no signal (same set)
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_write_idu_reads_merges_and_writes(hass):
    batches = {
        0: [1, 2, 22, 3, 25, 0] + [0] * (6 * 14),
    }
    client = _make_client(idu_batches=batches)
    coord = ZhijinglingCoordinator(hass, client=client, slave_id=1, entry_id="e1")

    # Populate current state
    await coord._async_update_data()

    await coord.async_write_idu(0, set_temp=24)
    client.write_registers.assert_awaited_once()
    args = client.write_registers.await_args
    assert args.args[0] == 4000  # base address for IDU 0
    assert args.args[1] == [1, 2, 24, 3]  # on_off, mode, new set_temp, fan_speed
