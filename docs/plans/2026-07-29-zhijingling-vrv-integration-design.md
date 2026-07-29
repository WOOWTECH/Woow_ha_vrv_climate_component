# 智精靈 VRV 閘道 Home Assistant Integration — Design

**Date:** 2026-07-29
**Author:** WOOWTECH
**Status:** Design approved, ready for implementation
**Repo:** https://github.com/WOOWTECH/Woow_ha_vrv_climate_component
**Reference implementation:** [woow_ha_atmocube](https://github.com/WOOWTECH/woow_ha_atmocube)

---

## 1. Goals

Ship a Home Assistant custom integration that:

- Talks to the **ZhiJingLing VRV Gateway (UACC-Bs-XX family)** over Modbus TCP.
- Exposes each connected indoor unit (IDU) as a `climate` entity.
- Handles **floating sub-devices** — the physical set of IDUs behind the gateway
  changes over time; the integration must discover new IDUs on the fly.
- Ships as a HACS-installable custom repo.

## 2. Non-goals (YAGNI)

- Support for other VRV brands / other gateway vendors.
- Automatic network discovery (mDNS / DHCP scan).
- Configuration UI beyond IP / port / slave.
- Broadcast service (write to all IDUs at once) — users can wrap it in HA
  automations if needed.
- Firmware / brand / product-type sensors — these change never (gateway
  never updates itself in the field).
- Options flow for polling interval / timeouts.

## 3. Target device

- **Model family:** ZhiJingLing UACC-Bs-XX (single-loop VRV gateway).
- **Transport:** Modbus TCP on port `502`, slave ID `1` by default.
- **Register map (per protocol doc `智精靈单路多联机对接协议0912`):**
  - **Gateway meta:** `2000..2005` — brand, product_type, IDU count,
    temperature min, temperature max, reserved.
  - **Read per IDU `n` (0-63):** `6n+0..5` — on_off, mode, set_temp,
    fan_speed, room_temp, fault_code.
  - **Write per IDU `n`:** `4000+4n+0..3` — on_off, mode, set_temp, fan_speed.
  - **Broadcast write (all IDUs):** `5000..5003` — same layout as per-IDU
    write. Not exposed.
- **Encodings:**
  - `on_off`: 0=關, 1=開
  - `mode`: 1=制熱, 2=制冷, 4=送風, 8=除濕 (bitmap-style values)
  - `temperature`: unsigned °C, direct value (0x14 = 20°C)
  - `fan_speed`: 0=自動, 1=低, 2=中, 3=高
  - `room_temp`: signed int16, -50..+50 °C
  - `fault_code`: brand-dependent, non-zero indicates fault

**Protocol edge cases:**
- Under `送風` mode, changes to temperature are ignored by the device.
- Under `除濕` mode, changes to fan speed are ignored.
- Fresh-air modules (if wired) expose additional mode values 0x10 / 0x20 / 0x30.
  Treat as unknown; UI shows nothing until we see one in the field.

## 4. Architecture

```
config_flow ─► ConfigEntry (host, port, slave_id)
                  │
                  ▼
        __init__.async_setup_entry
                  │
                  ├─► ZhijinglingCoordinator
                  │     • SCAN_INTERVAL = 10s
                  │     • reads regs 2000..2005 (gateway meta)
                  │     • reads regs 6n+0..5 in 4 batches for 64 IDUs
                  │     • detects online IDUs via room_temp!=0 heuristic
                  │     • tracks known_online_idus: set[int]
                  │     • dispatches SIGNAL_NEW_IDU when new slot goes online
                  │
                  └─► forward_entry_setups([climate, sensor])
                        │
                        ├─► climate.async_setup_entry
                        │     • subscribes to SIGNAL_NEW_IDU
                        │     • adds ZhijinglingClimate for each new IDU
                        │
                        └─► sensor.async_setup_entry
                              • adds 2 gateway-level diagnostic sensors
```

### 4.1 Coordinator responsibilities

- Own the `AsyncModbusTcpClient` life-cycle.
- On each refresh (every 10 s):
  1. Read `2000..2005` → `GatewayData` (brand, product_type, idu_total,
     temp_min, temp_max).
  2. Read `0..89`, `90..179`, `180..269`, `270..383` → parse 64 IDU states.
  3. For each IDU, compute `online = room_temp != 0 or on_off != 0 or fault_code != 0`.
  4. Compare `current_online` against `self._known_idus`; dispatch
     `SIGNAL_NEW_IDU` with the newly-online set.
- Expose write API:
  `async_write_idu(idu_id, *, on_off=None, mode=None, set_temp=None, fan_speed=None)`
  which reads the current 4-register write block, merges the passed fields,
  writes back via FC10, then calls `async_request_refresh()`.

### 4.2 Online detection heuristic

The MODBUS-TCP variant of the protocol has **no explicit online bitmap**
(CUSTOM-A does, but this is a different frame). The protocol doc explicitly
suggests "**通过温度非0判断**" as the detection method for IDU presence.
Combined with `reg 2002` for total IDU count, the check is:

```python
online = (room_temp != 0) or (on_off != 0) or (fault_code != 0)
```

Rationale: an unplugged / non-existent IDU slot returns all-zero registers.
Even a powered-off IDU will still report room_temp because the wired
communication bus reads the thermistor.

### 4.3 Offline handling

Once an IDU has been seen online at least once, its `climate` entity is
kept in the entity registry forever. When it goes offline again:

- `available = False`
- Entity remains in the registry
- User must manually remove via HA UI (device page → delete)

This matches VRV installation semantics — an IDU disappearing from the
Modbus bus usually means a cable fault, not that the IDU was removed.

### 4.4 Dynamic add mechanism

`async_dispatcher_send` / `async_dispatcher_connect` with signal
`f"{DOMAIN}_new_idu_{entry_id}"`. The climate platform listens; when a
new set of IDU IDs arrives, it constructs `ZhijinglingClimate` instances
and calls `async_add_entities`. This pattern is used by many official
integrations (Sonoff, Xiaomi Miio) and does not require re-loading the
integration.

## 5. Config flow

- Single `user` step. No discovery, no options flow.
- Fields: `host` (required), `port` (default 502), `slave_id` (default 1).
- Validation (level B):
  1. TCP connect to `{host}:{port}` with 5-second timeout.
  2. Read holding registers `2000..2005`.
  3. Assert `1 <= idu_total <= 64`.
  4. On failure, surface `cannot_connect` or `invalid_device` to the form.
- Unique ID: `f"{host}:{port}"`. `_abort_if_unique_id_configured()` blocks
  duplicate entries.
- Entry title: `f"智精靈閘道 ({host})"`.

## 6. Entities

### 6.1 `climate.ZhijinglingClimate` (one per IDU)

- `_attr_has_entity_name = True`, translation key `idu`.
- `device_info`:
  - `identifiers={(DOMAIN, f"{entry_id}_idu_{idu_id}")}`
  - `name=f"內機 {idu_id + 1}"` (1-indexed for humans)
  - `manufacturer="智精靈"`, `model=f"VRV IDU (slot {idu_id})"`
  - `via_device=(DOMAIN, f"{entry_id}_gateway")`
- Supported features:
  `TARGET_TEMPERATURE | FAN_MODE | TURN_ON | TURN_OFF`
- HVAC modes: `OFF, HEAT, COOL, FAN_ONLY, DRY`
- Fan modes: `AUTO, LOW, MEDIUM, HIGH`
- Range: `min_temp` / `max_temp` populated from `reg 2003 / 2004`
  (fallback 16 / 30). `target_temperature_step = 1`.
- Attributes: `fault_code` in `extra_state_attributes`.
- Set-temperature guard: reject with `ServiceValidationError` if current
  mode is `FAN_ONLY` (doc: `送風下改變溫度無效`).
- Set-fan guard: reject if current mode is `DRY` (doc: `除濕下改變風速無效`).

### 6.2 `sensor` (2 gateway-level diagnostic)

Attached to a synthetic gateway device
(`identifiers={(DOMAIN, f"{entry_id}_gateway")}`), so IDU devices can
`via_device` under it.

| Entity                         | Source                 | Class                 |
|--------------------------------|------------------------|-----------------------|
| `sensor.gateway_idu_total`     | `reg 2002`             | DIAGNOSTIC, MEASUREMENT |
| `sensor.gateway_idu_online`    | `len(coord.data.idus)` | DIAGNOSTIC, MEASUREMENT |

## 7. File layout

```
custom_components/zhijingling_vrv/
├── __init__.py              # async_setup_entry / async_unload_entry
├── manifest.json            # domain, requirements=pymodbus>=3.11.2
├── config_flow.py           # user step + validate
├── const.py                 # DOMAIN, SCAN_INTERVAL, MAX_IDUS, mode/fan tables
├── coordinator.py           # ZhijinglingCoordinator, IduState, GatewayData
├── climate.py               # ZhijinglingClimate + dispatcher setup
├── sensor.py                # gateway diagnostic sensors
├── strings.json
└── translations/
    ├── zh-Hant.json
    ├── zh-Hans.json
    └── en.json
```

Repo root:

```
Woow_ha_vrv_climate_component/
├── README.md                # install via HACS, config steps, register map ref
├── LICENSE                  # MIT (matching WOOWTECH org convention)
├── hacs.json                # HACS custom repo metadata
├── .github/workflows/
│   ├── hassfest.yaml        # HA integration validator
│   └── hacs.yaml            # HACS action validator
├── docs/
│   └── plans/               # design docs live here
└── custom_components/
    └── zhijingling_vrv/
```

## 8. Modbus interaction details

- **Client:** `pymodbus>=3.11.2` — `AsyncModbusTcpClient`.
- **Connection lifetime:** created in `async_setup_entry`, closed in
  `async_unload_entry`. Reused across every poll — no per-request reconnect.
- **Timeouts:** default (3 s) is fine; if a poll times out, `UpdateFailed`
  propagates and HA marks entities unavailable.
- **Batching:** four FC03 reads per poll, 90 registers each (15 IDUs ×
  6 regs). Batches: `0-89`, `90-179`, `180-269`, `270-359`. IDU 60-63 sits
  in `360-383` — folded into the last batch (24 regs padding is fine).
- **Write path:** FC10 (write multiple registers) with `count=4` starting at
  `4000 + 4*idu_id`. Never uses broadcast register 5000.

## 9. Error handling

| Scenario                              | Behavior                                                                            |
|---------------------------------------|-------------------------------------------------------------------------------------|
| TCP disconnect during poll            | `UpdateFailed` → all entities go unavailable → next poll retries                    |
| Modbus exception response on FC03     | Log at WARNING, keep last-known values for that IDU, do not fail whole poll         |
| Write FC10 returns exception          | Raise `HomeAssistantError` back to the service caller, log at ERROR                 |
| IDU seen online, then room_temp = 0   | Mark entity unavailable, keep in registry                                           |
| `reg 2002` reports `idu_total = 0`    | Config-flow validation rejects entry setup                                          |
| Reg 2003 / 2004 out of range          | Clamp to `[10, 40]` for `min_temp` / `max_temp`                                     |

## 10. Testing plan

- Local integration test against gateway `192.168.2.20:502` (the simulator
  variant currently on the bench, 64 virtual IDUs).
- Manual UI tests:
  - Add via `Settings → Devices → Add Integration → ZhiJingLing VRV`.
  - Confirm 64 climate entities appear.
  - Change mode on IDU 1 via UI; verify `mbpoll` read back matches.
  - Kill gateway TCP; verify all entities go unavailable within 30s.
  - Restore; verify entities recover on the next poll.
- HACS validation via GitHub Actions (`hacs.yaml` + `hassfest.yaml`).

## 11. Out-of-scope items tracked for possible v0.2

- Broadcast service `zhijingling_vrv.broadcast` (write regs 5000..5003).
- Automatic gateway discovery via UDP probe.
- Reading `inform.js` over HTTP to expose firmware / MAC as attributes.
- Handling fresh-air module mode values (0x10 / 0x20 / 0x30).
- Options flow to expose SCAN_INTERVAL.

## 12. Decision log

| # | Question                             | Choice                                              |
|---|--------------------------------------|-----------------------------------------------------|
| 1 | Scope                                | ZhiJingLing family only                             |
| 2 | Discovery                            | Manual IP only                                      |
| 3 | Online detection                     | `room_temp!=0 or on_off!=0 or fault!=0` heuristic   |
| 4 | Offline IDU handling                 | Unavailable + kept in registry; manual delete       |
| 5 | Entity structure per IDU             | `climate` only, fault in attributes                 |
| 6 | Gateway-level entities               | Gateway device + `idu_total`, `idu_online` sensors  |
| 7 | Polling interval                     | 10 s, force refresh after every write               |
| 8 | Initial entity creation              | Dynamic — dispatcher-based add for newly-online IDU |
| 9 | Config flow validation depth         | TCP + reg 2000..2005 read                           |
