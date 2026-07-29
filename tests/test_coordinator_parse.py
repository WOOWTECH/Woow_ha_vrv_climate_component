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
