# ZhiJingLing VRV Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a Home Assistant custom integration (`zhijingling_vrv`) that talks to the ZhiJingLing VRV gateway over Modbus TCP, exposes each IDU as a `climate` entity, dynamically adds newly-online IDUs via dispatcher signals, and ships as a HACS repo.

**Architecture:** Follow the design in `docs/plans/2026-07-29-zhijingling-vrv-integration-design.md`. Layered as `config_flow → ConfigEntry → DataUpdateCoordinator (owns pymodbus AsyncModbusTcpClient) → dispatcher → climate/sensor platforms`. Coordinator polls every 10 s, batches four FC03 reads for 64 IDU slots, and detects "online" via `room_temp != 0 or on_off != 0 or fault_code != 0`.

**Tech Stack:** Python 3.12+, Home Assistant 2024.10+, `pymodbus>=3.11.2`, `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component` (test harness).

**Test gateway:** `192.168.2.20:502` slave `1` (simulator variant with 64 virtual IDUs — safe to write to).

**Repo root:** `~/Desktop/Woow_ha_vrv_climate_component/` (already git-initialised, remote `origin` = `https://github.com/WOOWTECH/Woow_ha_vrv_climate_component`).

**Coding conventions:** Match [`woow_ha_atmocube`](https://github.com/WOOWTECH/woow_ha_atmocube):
- `_attr_has_entity_name = True`
- `entry.runtime_data` for coordinator storage (HA 2024.10+ pattern)
- `async_setup_entry` / `async_unload_entry` in `__init__.py`
- Snake_case Python, HA `entity_platform` / `entity_component` idioms.

---

## Task 0: Set up test harness

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.gitignore` (already exists — extend)

**Step 1: Write `pyproject.toml`**

```toml
[project]
name = "zhijingling_vrv"
version = "0.1.0"
description = "Home Assistant integration for ZhiJingLing VRV gateway"
requires-python = ">=3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: requires a live ZhiJingLing gateway at 192.168.2.20",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

**Step 2: Write `tests/__init__.py`**

```python
"""Tests for zhijingling_vrv."""
```

**Step 3: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Prevent pymodbus retry sleeps from stalling tests."""
    async def _sleep(_):
        return None

    monkeypatch.setattr("asyncio.sleep", _sleep)
```

**Step 4: Install dev deps in a venv**

Run:
```bash
cd ~/Desktop/Woow_ha_vrv_climate_component
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pytest pytest-asyncio pymodbus 'homeassistant>=2024.10.0' pytest-homeassistant-custom-component ruff
```

Expected: install completes, no errors.

**Step 5: Verify pytest discovers zero tests**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran`

**Step 6: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: add pytest harness"
```

---

## Task 1: `const.py` with mode/fan mapping

**Files:**
- Create: `custom_components/zhijingling_vrv/const.py`
- Create: `custom_components/zhijingling_vrv/__init__.py` (stub so the package is importable)
- Test: `tests/test_const.py`

**Step 1: Write failing test**

Create `tests/test_const.py`:

```python
"""Constants — mode/fan mapping."""
from __future__ import annotations

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

from custom_components.zhijingling_vrv.const import (
    FAN_DEVICE_TO_HA,
    FAN_HA_TO_DEVICE,
    MODE_DEVICE_TO_HA,
    MODE_HA_TO_DEVICE,
)


def test_mode_round_trip():
    for ha_mode, device_val in MODE_HA_TO_DEVICE.items():
        assert MODE_DEVICE_TO_HA[device_val] == ha_mode


def test_mode_device_values_match_protocol():
    assert MODE_HA_TO_DEVICE[HVACMode.HEAT] == 1
    assert MODE_HA_TO_DEVICE[HVACMode.COOL] == 2
    assert MODE_HA_TO_DEVICE[HVACMode.FAN_ONLY] == 4
    assert MODE_HA_TO_DEVICE[HVACMode.DRY] == 8


def test_fan_round_trip():
    for ha_fan, device_val in FAN_HA_TO_DEVICE.items():
        assert FAN_DEVICE_TO_HA[device_val] == ha_fan


def test_fan_device_values_match_protocol():
    assert FAN_HA_TO_DEVICE[FAN_AUTO] == 0
    assert FAN_HA_TO_DEVICE[FAN_LOW] == 1
    assert FAN_HA_TO_DEVICE[FAN_MEDIUM] == 2
    assert FAN_HA_TO_DEVICE[FAN_HIGH] == 3
```

**Step 2: Run test to see it fail**

Run: `.venv/bin/pytest tests/test_const.py -v`
Expected: FAIL with `ModuleNotFoundError` on `custom_components.zhijingling_vrv.const`.

**Step 3: Write `custom_components/zhijingling_vrv/__init__.py` stub**

```python
"""ZhiJingLing VRV integration package."""
```

**Step 4: Write `const.py`**

```python
"""Constants for the ZhiJingLing VRV integration."""
from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

DOMAIN: Final = "zhijingling_vrv"
MANUFACTURER: Final = "智精靈"

DEFAULT_PORT: Final = 502
DEFAULT_SLAVE_ID: Final = 1
SCAN_INTERVAL: Final = timedelta(seconds=10)
MAX_IDUS: Final = 64
BATCH_SIZE: Final = 15  # IDUs per FC03 read (× 6 registers = 90)

# Register layout (see docs/plans/2026-07-29-zhijingling-vrv-integration-design.md §3)
REG_GATEWAY_META: Final = 2000        # length 6
REG_IDU_READ_BASE: Final = 0          # per-IDU stride 6
REG_IDU_WRITE_BASE: Final = 4000      # per-IDU stride 4

# Fallback temperature range if gateway reports 0
DEFAULT_MIN_TEMP: Final = 16
DEFAULT_MAX_TEMP: Final = 30

# Signal names
SIGNAL_NEW_IDU: Final = f"{DOMAIN}_new_idu_{{entry_id}}"

# Protocol encoding tables
MODE_HA_TO_DEVICE: Final[dict[HVACMode, int]] = {
    HVACMode.HEAT: 1,
    HVACMode.COOL: 2,
    HVACMode.FAN_ONLY: 4,
    HVACMode.DRY: 8,
}
MODE_DEVICE_TO_HA: Final[dict[int, HVACMode]] = {v: k for k, v in MODE_HA_TO_DEVICE.items()}

FAN_HA_TO_DEVICE: Final[dict[str, int]] = {
    FAN_AUTO: 0,
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3,
}
FAN_DEVICE_TO_HA: Final[dict[int, str]] = {v: k for k, v in FAN_HA_TO_DEVICE.items()}
```

**Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_const.py -v`
Expected: PASS (4 tests).

**Step 6: Commit**

```bash
git add custom_components/zhijingling_vrv/__init__.py \
        custom_components/zhijingling_vrv/const.py \
        tests/test_const.py
git commit -m "feat(const): domain, mappings, register layout"
```

---

## Task 2: Coordinator — pure parsing functions

**Files:**
- Create: `custom_components/zhijingling_vrv/coordinator.py`
- Test: `tests/test_coordinator_parse.py`

**Step 1: Write failing tests for `parse_gateway_meta` and `parse_idu_batch`**

```python
"""Coordinator parsing — pure functions."""
from __future__ import annotations

from custom_components.zhijingling_vrv.coordinator import (
    GatewayData,
    IduState,
    parse_gateway_meta,
    parse_idu_batch,
    signed_int16,
)


def test_signed_int16_positive():
    assert signed_int16(0x0014) == 20


def test_signed_int16_negative():
    assert signed_int16(0xFFFE) == -2


def test_signed_int16_zero():
    assert signed_int16(0) == 0


def test_parse_gateway_meta():
    regs = [10, 20, 32, 16, 30, 0]
    meta = parse_gateway_meta(regs)
    assert meta == GatewayData(brand=10, product_type=20, idu_total=32, temp_min=16, temp_max=30)


def test_parse_idu_batch_reads_all_slots():
    # 2 IDUs worth: 12 regs
    # IDU 0: on=1 mode=2 set=22 fan=3 room=25 fault=0
    # IDU 1: all zero (offline)
    regs = [1, 2, 22, 3, 25, 0, 0, 0, 0, 0, 0, 0]
    states = parse_idu_batch(regs, first_idu_id=5, count=2)
    assert states[5] == IduState(
        idu_id=5, on_off=1, mode=2, set_temp=22, fan_speed=3, room_temp=25, fault_code=0
    )
    assert states[6] is None  # all-zero → offline


def test_parse_idu_batch_online_via_fault_only():
    # room_temp=0 but fault_code=5 → still online
    regs = [0, 0, 0, 0, 0, 5]
    states = parse_idu_batch(regs, first_idu_id=0, count=1)
    assert states[0] is not None
    assert states[0].fault_code == 5


def test_parse_idu_batch_negative_room_temp():
    regs = [1, 2, 20, 1, 0xFFFE, 0]  # room = -2
    states = parse_idu_batch(regs, first_idu_id=0, count=1)
    assert states[0].room_temp == -2
```

**Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/test_coordinator_parse.py -v`
Expected: FAIL — module missing.

**Step 3: Write minimal coordinator with just the parsers**

```python
"""ZhiJingLing VRV Modbus TCP data coordinator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def signed_int16(value: int) -> int:
    """Interpret a 16-bit unsigned register as signed int16."""
    return value - 0x10000 if value & 0x8000 else value


@dataclass(frozen=True, slots=True)
class GatewayData:
    brand: int
    product_type: int
    idu_total: int
    temp_min: int
    temp_max: int


@dataclass(frozen=True, slots=True)
class IduState:
    idu_id: int
    on_off: int
    mode: int
    set_temp: int
    fan_speed: int
    room_temp: int
    fault_code: int


def parse_gateway_meta(regs: list[int]) -> GatewayData:
    """Parse registers 2000..2005 into gateway metadata."""
    brand, product_type, idu_total, temp_min, temp_max, _reserved = regs[:6]
    return GatewayData(
        brand=brand,
        product_type=product_type,
        idu_total=idu_total,
        temp_min=temp_min,
        temp_max=temp_max,
    )


def _is_online(on_off: int, room_temp: int, fault_code: int) -> bool:
    return room_temp != 0 or on_off != 0 or fault_code != 0


def parse_idu_batch(
    regs: list[int], first_idu_id: int, count: int
) -> dict[int, IduState | None]:
    """Parse a batch of 6*count registers into per-IDU state (None if offline)."""
    result: dict[int, IduState | None] = {}
    for i in range(count):
        base = i * 6
        on_off, mode, set_temp, fan_speed, room_raw, fault_code = regs[base : base + 6]
        room_temp = signed_int16(room_raw)
        if not _is_online(on_off, room_temp, fault_code):
            result[first_idu_id + i] = None
            continue
        result[first_idu_id + i] = IduState(
            idu_id=first_idu_id + i,
            on_off=on_off,
            mode=mode,
            set_temp=set_temp,
            fan_speed=fan_speed,
            room_temp=room_temp,
            fault_code=fault_code,
        )
    return result
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_coordinator_parse.py -v`
Expected: PASS (6 tests).

**Step 5: Commit**

```bash
git add custom_components/zhijingling_vrv/coordinator.py tests/test_coordinator_parse.py
git commit -m "feat(coordinator): pure parsers for gateway meta and IDU batch"
```

---

## Task 3: Coordinator — Modbus polling class (unit-tested with fake client)

**Files:**
- Modify: `custom_components/zhijingling_vrv/coordinator.py`
- Test: `tests/test_coordinator_poll.py`

**Step 1: Write failing tests using a fake pymodbus client**

```python
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

    async def read_holding_registers(address, *, count, slave):
        if address == 2000:
            return _RegResponse(gateway_meta or [1, 1, 2, 16, 30, 0])
        if idu_batches and address in idu_batches:
            return _RegResponse(idu_batches[address])
        return _RegResponse([0] * count)

    async def write_registers(address, values, slave):
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
```

Note: `hass` fixture comes from `pytest-homeassistant-custom-component`.

**Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/test_coordinator_poll.py -v`
Expected: FAIL — `ZhijinglingCoordinator` not defined.

**Step 3: Extend `coordinator.py`**

Append:

```python
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BATCH_SIZE,
    DOMAIN,
    MAX_IDUS,
    REG_GATEWAY_META,
    REG_IDU_READ_BASE,
    REG_IDU_WRITE_BASE,
    SCAN_INTERVAL,
    SIGNAL_NEW_IDU,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoordinatorData:
    gateway: GatewayData
    idus: dict[int, IduState]


class ZhijinglingCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Poll a ZhiJingLing VRV gateway over Modbus TCP."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: Any,
        slave_id: int,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.slave_id = slave_id
        self.entry_id = entry_id
        self._known_idus: set[int] = set()

    def _dispatch(self, hass: HomeAssistant, signal: str, payload: Any) -> None:
        async_dispatcher_send(hass, signal, payload)

    async def _read(self, address: int, count: int) -> list[int]:
        resp = await self.client.read_holding_registers(
            address, count=count, slave=self.slave_id
        )
        if resp.isError():
            raise UpdateFailed(f"Modbus read {address}+{count} failed: {resp}")
        return list(resp.registers)

    async def _async_update_data(self) -> CoordinatorData:
        try:
            meta_regs = await self._read(REG_GATEWAY_META, 6)
            gateway = parse_gateway_meta(meta_regs)

            idus: dict[int, IduState] = {}
            for batch_start in range(0, MAX_IDUS, BATCH_SIZE):
                count = min(BATCH_SIZE, MAX_IDUS - batch_start)
                addr = REG_IDU_READ_BASE + batch_start * 6
                regs = await self._read(addr, count * 6)
                parsed = parse_idu_batch(regs, first_idu_id=batch_start, count=count)
                for idu_id, state in parsed.items():
                    if state is not None:
                        idus[idu_id] = state
        except Exception as err:
            raise UpdateFailed(str(err)) from err

        current_online = set(idus)
        new_idus = current_online - self._known_idus
        if new_idus:
            self._known_idus |= new_idus
            self._dispatch(
                self.hass,
                SIGNAL_NEW_IDU.format(entry_id=self.entry_id),
                new_idus,
            )

        return CoordinatorData(gateway=gateway, idus=idus)

    async def async_write_idu(
        self,
        idu_id: int,
        *,
        on_off: int | None = None,
        mode: int | None = None,
        set_temp: int | None = None,
        fan_speed: int | None = None,
    ) -> None:
        current = None if self.data is None else self.data.idus.get(idu_id)
        # Fall back to reading if we have no cached state
        if current is None:
            regs = await self._read(REG_IDU_READ_BASE + idu_id * 6, 6)
            parsed = parse_idu_batch(regs, first_idu_id=idu_id, count=1)
            current = parsed[idu_id]
        if current is None:
            raise RuntimeError(f"IDU {idu_id} offline; cannot write")

        payload = [
            on_off if on_off is not None else current.on_off,
            mode if mode is not None else current.mode,
            set_temp if set_temp is not None else current.set_temp,
            fan_speed if fan_speed is not None else current.fan_speed,
        ]
        addr = REG_IDU_WRITE_BASE + idu_id * 4
        resp = await self.client.write_registers(addr, payload, self.slave_id)
        if resp.isError():
            raise RuntimeError(f"Modbus write {addr} failed: {resp}")
        await self.async_request_refresh()
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_coordinator_poll.py -v`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add custom_components/zhijingling_vrv/coordinator.py tests/test_coordinator_poll.py
git commit -m "feat(coordinator): polling loop with dispatcher + write API"
```

---

## Task 4: Coordinator — live integration test

**Files:**
- Test: `tests/test_coordinator_live.py`

**Step 1: Write live-gateway integration test**

```python
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
        await coord._async_update_data()
        # Toggle IDU 0 setpoint 22 → 23 → back to original
        original = coord.data.idus[0].set_temp
        await coord.async_write_idu(0, set_temp=23)
        await coord.async_refresh()
        assert coord.data.idus[0].set_temp == 23
        await coord.async_write_idu(0, set_temp=original)
    finally:
        client.close()
```

**Step 2: Run integration tests**

Run: `.venv/bin/pytest tests/test_coordinator_live.py -v -m integration`
Expected: PASS.

If the gateway is unreachable, skip and diagnose. Do not modify the test to pass; fix the connectivity first.

**Step 3: Commit**

```bash
git add tests/test_coordinator_live.py
git commit -m "test(coordinator): live gateway integration tests"
```

---

## Task 5: Config flow

**Files:**
- Create: `custom_components/zhijingling_vrv/config_flow.py`
- Test: `tests/test_config_flow.py`

**Step 1: Write failing tests**

```python
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
async def test_user_flow_success(hass):
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
async def test_user_flow_cannot_connect(hass):
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
async def test_user_flow_invalid_device(hass):
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
```

**Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/test_config_flow.py -v`
Expected: FAIL — `config_flow` module missing.

**Step 3: Write `config_flow.py`**

```python
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
        resp = await client.read_holding_registers(2000, count=6, slave=slave_id)
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
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_config_flow.py -v`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add custom_components/zhijingling_vrv/config_flow.py tests/test_config_flow.py
git commit -m "feat(config_flow): user step with TCP + reg 2000 validation"
```

---

## Task 6: `__init__.py` — entry setup/unload

**Files:**
- Modify: `custom_components/zhijingling_vrv/__init__.py`

**Step 1: Replace stub with the real setup**

```python
"""ZhiJingLing VRV integration setup."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from pymodbus.client import AsyncModbusTcpClient

from .config_flow import CONF_SLAVE_ID
from .coordinator import ZhijinglingCoordinator

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]


@dataclass
class RuntimeData:
    coordinator: ZhijinglingCoordinator
    client: AsyncModbusTcpClient


type ZhijinglingConfigEntry = ConfigEntry[RuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ZhijinglingConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    slave_id = entry.data[CONF_SLAVE_ID]

    client = AsyncModbusTcpClient(host, port=port, timeout=5)
    if not await client.connect():
        return False

    coordinator = ZhijinglingCoordinator(
        hass, client=client, slave_id=slave_id, entry_id=entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RuntimeData(coordinator=coordinator, client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZhijinglingConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and entry.runtime_data is not None:
        entry.runtime_data.client.close()
    return ok
```

**Step 2: Sanity — import the package under pytest**

Run: `.venv/bin/pytest --collect-only -q`
Expected: no import errors.

**Step 3: Commit**

```bash
git add custom_components/zhijingling_vrv/__init__.py
git commit -m "feat: async_setup_entry/unload with pymodbus client lifecycle"
```

---

## Task 7: `climate.py` platform

**Files:**
- Create: `custom_components/zhijingling_vrv/climate.py`
- Test: `tests/test_climate.py`

**Step 1: Write failing tests for property extraction**

```python
"""Climate entity."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.climate import FAN_HIGH, HVACMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.zhijingling_vrv.climate import ZhijinglingClimate
from custom_components.zhijingling_vrv.coordinator import (
    CoordinatorData,
    GatewayData,
    IduState,
)


def _coord_with_idu(idu: IduState) -> MagicMock:
    coord = MagicMock()
    coord.entry_id = "e1"
    coord.data = CoordinatorData(
        gateway=GatewayData(brand=1, product_type=1, idu_total=1, temp_min=16, temp_max=30),
        idus={idu.idu_id: idu},
    )
    return coord


def test_hvac_mode_reads_off_when_switch_off():
    coord = _coord_with_idu(
        IduState(idu_id=0, on_off=0, mode=2, set_temp=22, fan_speed=1, room_temp=25, fault_code=0)
    )
    entity = ZhijinglingClimate(coord, 0)
    assert entity.hvac_mode == HVACMode.OFF


def test_hvac_mode_reads_cool_when_on():
    coord = _coord_with_idu(
        IduState(idu_id=0, on_off=1, mode=2, set_temp=22, fan_speed=3, room_temp=25, fault_code=0)
    )
    entity = ZhijinglingClimate(coord, 0)
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.current_temperature == 25
    assert entity.target_temperature == 22
    assert entity.fan_mode == FAN_HIGH


def test_available_false_when_idu_offline():
    coord = MagicMock()
    coord.entry_id = "e1"
    coord.data = CoordinatorData(
        gateway=GatewayData(brand=1, product_type=1, idu_total=1, temp_min=16, temp_max=30),
        idus={},
    )
    entity = ZhijinglingClimate(coord, 0)
    assert entity.available is False


@pytest.mark.asyncio
async def test_set_temperature_rejected_in_fan_only():
    idu = IduState(idu_id=0, on_off=1, mode=4, set_temp=22, fan_speed=1, room_temp=25, fault_code=0)
    coord = _coord_with_idu(idu)
    entity = ZhijinglingClimate(coord, 0)
    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(temperature=24)
```

**Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/test_climate.py -v`
Expected: FAIL — `climate.py` missing.

**Step 3: Write `climate.py`**

```python
"""ZhiJingLing VRV climate platform."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    FAN_AUTO,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZhijinglingConfigEntry
from .const import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
    FAN_DEVICE_TO_HA,
    FAN_HA_TO_DEVICE,
    MANUFACTURER,
    MODE_DEVICE_TO_HA,
    MODE_HA_TO_DEVICE,
    SIGNAL_NEW_IDU,
)
from .coordinator import ZhijinglingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZhijinglingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord = entry.runtime_data.coordinator

    @callback
    def _add(idu_ids: set[int]) -> None:
        async_add_entities(ZhijinglingClimate(coord, i) for i in sorted(idu_ids))

    _add(set(coord.data.idus))
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_IDU.format(entry_id=entry.entry_id),
            _add,
        )
    )


class ZhijinglingClimate(CoordinatorEntity[ZhijinglingCoordinator], ClimateEntity):
    """One climate entity per IDU."""

    _attr_has_entity_name = True
    _attr_translation_key = "idu"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.FAN_ONLY,
        HVACMode.DRY,
    ]
    _attr_fan_modes = list(FAN_HA_TO_DEVICE.keys())
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: ZhijinglingCoordinator, idu_id: int) -> None:
        super().__init__(coordinator)
        self._idu_id = idu_id
        self._attr_unique_id = f"{coordinator.entry_id}_idu_{idu_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry_id}_idu_{idu_id}")},
            name=f"內機 {idu_id + 1}",
            manufacturer=MANUFACTURER,
            model=f"VRV IDU (slot {idu_id})",
            via_device=(DOMAIN, f"{coordinator.entry_id}_gateway"),
        )

    @property
    def _idu(self):
        return self.coordinator.data.idus.get(self._idu_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self._idu is not None

    @property
    def min_temp(self) -> float:
        gw = self.coordinator.data.gateway if self.coordinator.data else None
        return float(gw.temp_min) if gw and gw.temp_min else DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        gw = self.coordinator.data.gateway if self.coordinator.data else None
        return float(gw.temp_max) if gw and gw.temp_max else DEFAULT_MAX_TEMP

    @property
    def current_temperature(self) -> float | None:
        return None if self._idu is None else float(self._idu.room_temp)

    @property
    def target_temperature(self) -> float | None:
        return None if self._idu is None else float(self._idu.set_temp)

    @property
    def hvac_mode(self) -> HVACMode:
        if self._idu is None or self._idu.on_off == 0:
            return HVACMode.OFF
        return MODE_DEVICE_TO_HA.get(self._idu.mode, HVACMode.OFF)

    @property
    def fan_mode(self) -> str:
        if self._idu is None:
            return FAN_AUTO
        return FAN_DEVICE_TO_HA.get(self._idu.fan_speed, FAN_AUTO)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._idu is None:
            return {}
        return {"fault_code": self._idu.fault_code, "raw_mode": self._idu.mode}

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_write_idu(self._idu_id, on_off=0)
            return
        device_mode = MODE_HA_TO_DEVICE.get(hvac_mode)
        if device_mode is None:
            raise ServiceValidationError(f"Unsupported mode: {hvac_mode}")
        await self.coordinator.async_write_idu(self._idu_id, on_off=1, mode=device_mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if self.hvac_mode == HVACMode.FAN_ONLY:
            raise ServiceValidationError(
                "Cannot change setpoint while in FAN_ONLY mode"
            )
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.coordinator.async_write_idu(self._idu_id, set_temp=int(temp))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if self.hvac_mode == HVACMode.DRY:
            raise ServiceValidationError("Cannot change fan while in DRY mode")
        val = FAN_HA_TO_DEVICE.get(fan_mode)
        if val is None:
            raise ServiceValidationError(f"Unsupported fan mode: {fan_mode}")
        await self.coordinator.async_write_idu(self._idu_id, fan_speed=val)

    async def async_turn_on(self) -> None:
        await self.coordinator.async_write_idu(self._idu_id, on_off=1)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_write_idu(self._idu_id, on_off=0)
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_climate.py -v`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add custom_components/zhijingling_vrv/climate.py tests/test_climate.py
git commit -m "feat(climate): one climate entity per IDU + dispatcher-driven add"
```

---

## Task 8: `sensor.py` — gateway diagnostic sensors

**Files:**
- Create: `custom_components/zhijingling_vrv/sensor.py`
- Test: `tests/test_sensor.py`

**Step 1: Write failing test**

```python
"""Gateway diagnostic sensors."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.zhijingling_vrv.coordinator import CoordinatorData, GatewayData, IduState
from custom_components.zhijingling_vrv.sensor import IduOnlineSensor, IduTotalSensor


def _coord(total: int, online: dict[int, IduState]) -> MagicMock:
    c = MagicMock()
    c.entry_id = "e1"
    c.data = CoordinatorData(
        gateway=GatewayData(brand=1, product_type=1, idu_total=total, temp_min=16, temp_max=30),
        idus=online,
    )
    return c


def test_idu_total_reads_gateway_field():
    coord = _coord(total=32, online={})
    entity = IduTotalSensor(coord)
    assert entity.native_value == 32


def test_idu_online_counts_populated_idus():
    coord = _coord(
        total=32,
        online={
            0: IduState(0, 1, 2, 22, 3, 25, 0),
            5: IduState(5, 1, 2, 22, 3, 25, 0),
        },
    )
    entity = IduOnlineSensor(coord)
    assert entity.native_value == 2
```

**Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/test_sensor.py -v`
Expected: FAIL — module missing.

**Step 3: Write `sensor.py`**

```python
"""ZhiJingLing VRV gateway diagnostic sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZhijinglingConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import ZhijinglingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZhijinglingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord = entry.runtime_data.coordinator
    async_add_entities([IduTotalSensor(coord), IduOnlineSensor(coord)])


def _gateway_device(coord: ZhijinglingCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coord.entry_id}_gateway")},
        name="智精靈 VRV 閘道",
        manufacturer=MANUFACTURER,
        model="UACC-Bs-XX",
    )


class _GatewaySensor(CoordinatorEntity[ZhijinglingCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZhijinglingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = _gateway_device(coordinator)


class IduTotalSensor(_GatewaySensor):
    def __init__(self, coordinator: ZhijinglingCoordinator) -> None:
        super().__init__(coordinator, "idu_total")

    @property
    def native_value(self) -> int | None:
        return None if self.coordinator.data is None else self.coordinator.data.gateway.idu_total


class IduOnlineSensor(_GatewaySensor):
    def __init__(self, coordinator: ZhijinglingCoordinator) -> None:
        super().__init__(coordinator, "idu_online")

    @property
    def native_value(self) -> int | None:
        return None if self.coordinator.data is None else len(self.coordinator.data.idus)
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_sensor.py -v`
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add custom_components/zhijingling_vrv/sensor.py tests/test_sensor.py
git commit -m "feat(sensor): gateway idu_total + idu_online diagnostic sensors"
```

---

## Task 9: `strings.json` + translations

**Files:**
- Create: `custom_components/zhijingling_vrv/strings.json`
- Create: `custom_components/zhijingling_vrv/translations/en.json`
- Create: `custom_components/zhijingling_vrv/translations/zh-Hant.json`
- Create: `custom_components/zhijingling_vrv/translations/zh-Hans.json`

**Step 1: Write `strings.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "ZhiJingLing VRV Gateway",
        "data": {
          "host": "Gateway IP",
          "port": "Modbus TCP port",
          "slave_id": "Modbus slave ID"
        }
      }
    },
    "error": {
      "cannot_connect": "Cannot connect. Check the IP and that Modbus TCP is enabled on the gateway.",
      "invalid_device": "Connected but the device does not look like a ZhiJingLing gateway.",
      "unknown": "Unexpected error."
    },
    "abort": {
      "already_configured": "This gateway is already configured."
    }
  },
  "entity": {
    "climate": {
      "idu": { "name": "IDU {idu_id}" }
    },
    "sensor": {
      "idu_total": { "name": "IDU total" },
      "idu_online": { "name": "IDUs online" }
    }
  }
}
```

**Step 2: Write `translations/en.json`** — copy of `strings.json`.

**Step 3: Write `translations/zh-Hant.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "智精靈 VRV 閘道",
        "data": {
          "host": "閘道 IP",
          "port": "Modbus TCP 埠",
          "slave_id": "Modbus Slave ID"
        }
      }
    },
    "error": {
      "cannot_connect": "無法連線。請確認 IP，並確認閘道已啟用 Modbus TCP。",
      "invalid_device": "已連線，但裝置看起來不是智精靈閘道。",
      "unknown": "未預期的錯誤。"
    },
    "abort": {
      "already_configured": "此閘道已被加入。"
    }
  },
  "entity": {
    "climate": {
      "idu": { "name": "內機 {idu_id}" }
    },
    "sensor": {
      "idu_total": { "name": "內機總數" },
      "idu_online": { "name": "在線內機數" }
    }
  }
}
```

**Step 4: Write `translations/zh-Hans.json`** — same as zh-Hant but with 智精灵 / 内机 / 网关 / 号 (simplified).

**Step 5: Commit**

```bash
git add custom_components/zhijingling_vrv/strings.json \
        custom_components/zhijingling_vrv/translations/
git commit -m "feat(i18n): strings + en / zh-Hant / zh-Hans translations"
```

---

## Task 10: End-to-end smoke test in a live HA container

**Prerequisite:** dev HA instance available (see `ha-components-dev-run` skill in this workspace).

**Step 1: Copy the component into the HA config dir**

Assuming HA config is at `~/Desktop/woow_ha_2026_03/config/`:

```bash
rm -rf ~/Desktop/woow_ha_2026_03/config/custom_components/zhijingling_vrv
cp -r ~/Desktop/Woow_ha_vrv_climate_component/custom_components/zhijingling_vrv \
       ~/Desktop/woow_ha_2026_03/config/custom_components/
```

**Step 2: Restart HA**

Use the ha-components-dev-run skill's HA-restart procedure (or docker compose restart).

**Step 3: Add the integration through UI**

*Settings → Devices & Services → + Add integration → search "ZhiJingLing VRV"* → enter host `192.168.2.20`.

Expected:
- Setup succeeds.
- ≥ 1 `climate.內機_1` (etc.) entity appears.
- `sensor.gateway_idu_total`, `sensor.gateway_idu_online` appear.
- All entities are `available`.

**Step 4: Exercise write path in the UI**

- Change one IDU's mode from OFF → COOL. Confirm the change surfaces in the entity state within ~10 s.
- Change setpoint from 22 → 24. Confirm.
- Toggle turn on / turn off. Confirm.

**Step 5: Kill-restore test**

- Block `192.168.2.20` via `iptables` (or unplug USB Ethernet).
- Wait ~30 s. Confirm all climate entities go `unavailable`.
- Restore. Confirm entities recover on the next poll.

**Step 6: Document any surprises**

If anything fails, capture the HA log (`docker compose logs`) and open a new plan step to fix. Do not push if smoke fails.

**Step 7: Commit smoke evidence (screenshot in `docs/` optional)**

```bash
git commit --allow-empty -m "test: smoke test passed against 192.168.2.20"
git push
```

---

## Post-implementation

- Push all commits: `cd ~/Desktop/Woow_ha_vrv_climate_component && git push`.
- Confirm hassfest + hacs GitHub Actions pass on the PR / main branch.
- Bump README with an *Install via HACS* screenshot once verified.
- Tag `v0.1.0`.
