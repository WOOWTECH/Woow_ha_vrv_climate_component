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
