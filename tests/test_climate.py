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
