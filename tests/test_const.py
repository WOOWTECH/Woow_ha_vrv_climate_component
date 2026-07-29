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
