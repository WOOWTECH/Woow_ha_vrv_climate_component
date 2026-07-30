# Architecture

Deep-dive on the internal design of the `zhijingling_vrv` custom integration. Covers setup lifecycle, coordinator polling, entity model, and failure modes. For the register-level view see [`protocol.md`](protocol.md); for wiring HA to a live gateway see [`installation.md`](installation.md).

## 1. High-level view

```mermaid
flowchart LR
    A[User] -->|Add integration| CF[config_flow.py]
    CF -->|validated| ENT[ConfigEntry]
    ENT -->|__init__.async_setup_entry| CLIENT[AsyncModbusTcpClient]
    ENT --> COORD[ZhijinglingCoordinator]
    COORD -->|async_add_entities| CLIM[climate.py: ZhijinglingClimate]
    COORD -->|async_add_entities| SENS[sensor.py: diagnostics]
    COORD <-->|FC03 read / FC16 write| GW[智精靈 Gateway]
    GW <--> BUS[VRV bus]
    BUS <--> IDU[IDU 1..64]

    classDef ha fill:#41BDF5,color:#fff,stroke:#00579C
    classDef int fill:#8BC34A,stroke:#33691E
    classDef net fill:#FFB74D,stroke:#E65100
    class A,CF,ENT,CLIM,SENS,COORD ha
    class CLIENT,GW,BUS,IDU net
```

## 2. Setup lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant HA as HA Core
    participant CF as config_flow
    participant INIT as __init__
    participant CLI as AsyncModbusTcpClient
    participant COORD as Coordinator

    U->>HA: Add integration → ZhiJingLing VRV
    HA->>CF: async_step_user
    CF->>CLI: connect(host, port)
    CLI-->>CF: connected
    CF->>CLI: read_holding_registers(2000, 6)
    CLI-->>CF: [_, _, idu_total, _, _, _]
    CF->>CF: assert 1 ≤ idu_total ≤ 64
    CF-->>HA: create_entry(title="智精靈閘道 (host)")
    HA->>INIT: async_setup_entry(entry)
    INIT->>CLI: AsyncModbusTcpClient(host, port, timeout=5)
    CLI-->>INIT: connect() → True
    INIT->>COORD: __init__(client, slave_id, entry_id)
    INIT->>COORD: async_config_entry_first_refresh()
    COORD->>CLI: FC03 (batched, 5 reads)
    CLI-->>COORD: registers
    COORD->>COORD: parse → CoordinatorData
    INIT->>HA: forward_entry_setups(CLIMATE, SENSOR)
    HA->>CLIM: async_setup_entry
    HA->>SENS: async_setup_entry
    Note over CLIM,SENS: Entities register with HA state machine
```

Key API touch points:

- `config_flow.ZhijinglingConfigFlow` — validates handshake, sets a unique ID of `host:port`, prevents duplicate config entries
- `__init__.async_setup_entry` — creates the `AsyncModbusTcpClient`, boots the coordinator, and forwards to the `climate` + `sensor` platforms
- `__init__.async_unload_entry` — cleans up the client on integration removal / reload

## 3. Coordinator: polling model

```mermaid
flowchart TB
    START[Every SCAN_INTERVAL = 10 s]
    -->|_async_update_data| META[Read gateway meta: FC03 @ 2000, qty 6]
    --> PARSE_META[parse_gateway_meta → GatewayData]
    --> LOOP[For batch_start in 0..64 step 15]
    LOOP --> READ[FC03 @ batch_start*6, qty count*6]
    READ --> PARSE[parse_idu_batch → dict[int, IduState|None]]
    PARSE -->|_is_online| FILTER[Keep only online IDUs]
    FILTER --> NEXT{More batches?}
    NEXT -->|yes| LOOP
    NEXT -->|no| DIFF[current_online − _known_idus = new_idus]
    DIFF -->|new_idus non-empty| DISPATCH[async_dispatcher_send SIGNAL_NEW_IDU]
    DIFF --> RET[return CoordinatorData]
```

### Register access constants (from `const.py`)

| Constant | Value | Meaning |
|----------|-------|---------|
| `SCAN_INTERVAL` | `timedelta(seconds=10)` | Coordinator poll cadence |
| `MAX_IDUS` | 64 | Hard cap enforced by config flow validation |
| `BATCH_SIZE` | 15 | IDUs per FC03 read; 15 × 6 = 90 regs, safely under 125-reg FC03 limit |
| `REG_GATEWAY_META` | 2000 | Base of gateway metadata |
| `REG_IDU_READ_BASE` | 0 | Base of per-IDU read block |
| `REG_IDU_WRITE_BASE` | 4000 | Base of per-IDU write block |

### Write path (`async_write_idu`)

```mermaid
flowchart TB
    IN[async_write_idu idu_id, on_off?, mode?, set_temp?, fan_speed?]
    IN --> CACHE{cached self.data.idus[idu_id]?}
    CACHE -->|hit| MERGE
    CACHE -->|miss| FB[FC03 @ REG_IDU_READ_BASE + idu_id*6, qty 6]
    FB --> PIB[parse_idu_batch count=1]
    PIB --> ONL{IduState is None?}
    ONL -->|yes| RAISE[raise HomeAssistantError IDU offline]
    ONL -->|no| MERGE[merge args with cached IduState]
    MERGE --> WRITE[FC16 @ REG_IDU_WRITE_BASE + idu_id*4, payload=4 regs]
    WRITE -->|OK| REF[async_refresh → immediate poll]
    WRITE -->|error| RAISE2[raise HomeAssistantError Modbus write failed]
```

Writes are idempotent from the caller's point of view: even a single-field update (e.g. only `set_temp=24`) is serialized as the full `[on_off, mode, set_temp, fan_speed]` payload, so the coordinator's local cache never desyncs from the gateway.

## 4. Entity model

```mermaid
classDiagram
    class CoordinatorEntity {
        <<HA base>>
        available: bool
        async_added_to_hass()
    }
    class ClimateEntity {
        <<HA base>>
        hvac_modes
        fan_modes
        supported_features
        current_temperature
        target_temperature
        hvac_mode
        fan_mode
    }
    class ZhijinglingClimate {
        _idu_id: int
        _attr_unique_id
        _attr_device_info
        _idu(): IduState | None
        available: bool
        min_temp: float
        max_temp: float
        current_temperature: float | None
        target_temperature: float | None
        hvac_mode: HVACMode
        fan_mode: str
        extra_state_attributes: dict
        async_set_hvac_mode(mode)
        async_set_temperature(**kwargs)
        async_set_fan_mode(fan_mode)
        async_turn_on()
        async_turn_off()
    }
    CoordinatorEntity <|-- ZhijinglingClimate
    ClimateEntity <|-- ZhijinglingClimate
```

### Guarded transitions

Two vendor-imposed rules are enforced client-side to avoid gateway rejections:

- `async_set_temperature` raises `ServiceValidationError` if `hvac_mode == FAN_ONLY`
- `async_set_fan_mode` raises `ServiceValidationError` if `hvac_mode == DRY`

Users who need to override these must first switch mode.

### Device registry

Each `ZhijinglingClimate` declares a `DeviceInfo` with:

- `identifiers = {(DOMAIN, f"{entry_id}_idu_{idu_id}")}` — one device per IDU
- `via_device = (DOMAIN, f"{entry_id}_gateway")` — points at the (currently implicit) gateway hub device
- `name = 內機 N` (0-indexed slot + 1) — matches vendor-issued labels
- `manufacturer = 智精靈`, `model = VRV IDU (slot N)`

## 5. Dynamic IDU addition

```mermaid
sequenceDiagram
    autonumber
    participant COORD as Coordinator
    participant HA as HA dispatcher
    participant PLAT as climate.py async_setup_entry
    Note over COORD: batch parse detects IDU 47 online
    COORD->>COORD: new_idus = {47} − _known_idus
    COORD->>COORD: _known_idus |= {47}
    COORD->>HA: async_dispatcher_send(SIGNAL_NEW_IDU, {47})
    HA->>PLAT: _add({47})
    PLAT->>PLAT: new = {47} − added = {47}
    PLAT->>PLAT: async_add_entities(ZhijinglingClimate(coord, 47))
    Note over PLAT: HA registers climate.nei_ji_47
```

Signal name: `zhijingling_vrv_new_idu_{entry_id}` — namespaced by entry so multiple gateway entries don't cross-talk. Subscribers are cleaned up automatically by `entry.async_on_unload`.

## 6. Failure model

```mermaid
stateDiagram-v2
    [*] --> Healthy
    Healthy --> Reading: SCAN_INTERVAL tick
    Reading --> Healthy: FC03 success
    Reading --> UpdateFailed: TCP timeout / Modbus exception
    UpdateFailed --> Unavailable: DataUpdateCoordinator marks entities unavailable
    Unavailable --> Reading: next SCAN_INTERVAL tick
    Reading --> Healthy: FC03 success again — state restored from cached IduState + fresh regs
    Healthy --> WriteRequested: service call
    WriteRequested --> Healthy: FC16 ACK + async_refresh
    WriteRequested --> WriteError: gateway rejects / IDU offline / timeout
    WriteError --> Healthy: raise HomeAssistantError / ServiceValidationError to caller
```

The coordinator wraps every read in `UpdateFailed(...)` — HA's standard mechanism for signalling entity unavailability. During the outage:

- All child entities report `available = False`
- Automations that depend on `not is_state('climate.nei_ji_1', 'unavailable')` short-circuit correctly
- No stale values are exposed to Lovelace

On recovery, the very next successful poll fully rehydrates state — no explicit reconnect logic needed.

## 7. Troubleshooting

### Enable debug logs

Add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.zhijingling_vrv: debug
    pymodbus: warning
```

### Common issues

| Log line | Meaning | Action |
|----------|---------|--------|
| `Modbus read 2000+6 failed: ModbusIOException(...)` | Handshake failed | Check TCP connectivity, gateway Modbus mode |
| `Modbus read N+90 failed: ...` | Mid-batch read failed | Coordinator will retry on next tick; look for LAN issues |
| `Update failed for zhijingling_vrv_<entry>` | Entire poll cycle aborted | Entities go unavailable; investigate network + gateway logs |
| `IDU N offline; cannot write` | Write attempted on filtered-out IDU | Confirm IDU is powered and appears in next poll |
| `Detected that custom integration 'zhijingling_vrv' calls device_registry.async_get_or_create referencing a non existing via_device` | Known 0.1.0 issue — gateway hub device not registered explicitly | Non-blocking; scheduled fix before HA 2025.12 |

### Verify from HA host

```bash
# TCP reachability
nc -vz 192.168.2.20 502

# Modbus handshake (with mbpoll or similar)
mbpoll -a 1 -t 3 -r 2001 -c 6 192.168.2.20
# Register 2001 = idu_total (1-based); expect 1..64
```

### Reset state

- **Reload integration:** Settings → Devices & Services → ZhiJingLing VRV → ⋮ → Reload
- **Remove entities:** Settings → Devices & Services → Entities → filter by integration → select → Delete
- **Remove integration:** Settings → Devices & Services → ⋮ → Delete — removes entities, devices, and disconnects the Modbus client

---

Cross-refs: [`protocol.md`](protocol.md) · [`installation.md`](installation.md) · [`smoke-test-2026-07-29.md`](smoke-test-2026-07-29.md)
