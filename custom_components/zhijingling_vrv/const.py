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
