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
from .coordinator import IduState, ZhijinglingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZhijinglingConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord = entry.runtime_data.coordinator
    added: set[int] = set()

    @callback
    def _add(idu_ids: set[int]) -> None:
        new = idu_ids - added
        if not new:
            return
        added.update(new)
        async_add_entities(ZhijinglingClimate(coord, i) for i in sorted(new))

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
        self._attr_translation_placeholders = {"idu_id": str(idu_id + 1)}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry_id}_idu_{idu_id}")},
            name=f"內機 {idu_id + 1}",
            manufacturer=MANUFACTURER,
            model=f"VRV IDU (slot {idu_id})",
            via_device=(DOMAIN, f"{coordinator.entry_id}_gateway"),
        )

    @property
    def _idu(self) -> IduState | None:
        return self.coordinator.data.idus.get(self._idu_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self._idu is not None

    @property
    def min_temp(self) -> float:
        """Return the minimum settable temperature.

        Falls back to DEFAULT_MIN_TEMP when the gateway reports 0
        (unset sentinel — no installer-programmed range).
        """
        gw = self.coordinator.data.gateway if self.coordinator.data else None
        return float(gw.temp_min) if gw and gw.temp_min else DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum settable temperature.

        Falls back to DEFAULT_MAX_TEMP when the gateway reports 0
        (unset sentinel — no installer-programmed range).
        """
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
