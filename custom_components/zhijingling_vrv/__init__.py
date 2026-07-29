"""ZhiJingLing VRV integration setup."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
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
        raise ConfigEntryNotReady(f"Cannot connect to {host}:{port}")

    coordinator = ZhijinglingCoordinator(
        hass, client=client, slave_id=slave_id, entry_id=entry.entry_id
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        client.close()
        raise

    entry.runtime_data = RuntimeData(coordinator=coordinator, client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZhijinglingConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry.runtime_data.client.close()
    return ok
