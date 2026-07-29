"""ZhiJingLing VRV Modbus TCP data coordinator."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
            _LOGGER.exception("Update failed for %s", self.name)
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
            raise HomeAssistantError(f"IDU {idu_id} offline; cannot write")

        payload = [
            on_off if on_off is not None else current.on_off,
            mode if mode is not None else current.mode,
            set_temp if set_temp is not None else current.set_temp,
            fan_speed if fan_speed is not None else current.fan_speed,
        ]
        addr = REG_IDU_WRITE_BASE + idu_id * 4
        resp = await self.client.write_registers(addr, payload, self.slave_id)
        if resp.isError():
            raise HomeAssistantError(f"Modbus write {addr} failed: {resp}")
        await self.async_refresh()
