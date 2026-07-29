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
