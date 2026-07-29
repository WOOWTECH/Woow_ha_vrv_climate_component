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
