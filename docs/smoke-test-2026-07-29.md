# ZhiJingLing VRV Integration — Smoke Test 2026-07-29

**Target:** Live HAOS at 192.168.2.27 (HA Core 2026.4.2, Asia/Taipei)
**Gateway:** 智精靈 VRV Modbus TCP gateway at 192.168.2.20:502, slave_id=1
**Component version:** 0.1.0 (git b13acba)
**Deploy path:** `/config/custom_components/zhijingling_vrv/`

## 1. Config Flow — via REST (SUPERVISOR_TOKEN from a0d7b954_ssh add-on)

```
POST /api/config/config_entries/flow  {"handler":"zhijingling_vrv"}
→ flow_id 01KYQ4GCMFKD5DQK2D2KXQHSEX, step "user"

POST /api/config/config_entries/flow/01KYQ4GCMFKD5DQK2D2KXQHSEX
  {"host":"192.168.2.20","port":502,"slave_id":1}
→ type=create_entry  state=loaded
  entry_id 01KYQ4GME6AHAN3AZ0QG59Z9JN  title "智精靈閘道 (192.168.2.20)"
```

## 2. Entity Discovery

- **64 climate entities:** `climate.nei_ji_1` … `climate.nei_ji_64` (friendly names 內機 1 … 內機 64)
- **2 diagnostic sensors:**
  - `sensor.zhi_jing_ling_vrv_zha_dao_idu_total` = 64
  - `sensor.zhi_jing_ling_vrv_zha_dao_idus_online` = 64

Initial states: IDU 1 = off; IDU 2–64 = cool.

## 3. Write Path — climate.nei_ji_1 (baseline off / setpoint 25 / fan high)

| Step | Service call                                                | Post-write state                                     |
|------|-------------------------------------------------------------|------------------------------------------------------|
| 1    | `climate.set_hvac_mode` `hvac_mode: cool`                   | state=cool, temperature=25.0, fan_mode=high          |
| 2    | `climate.set_temperature` `temperature: 24`                 | state=cool, temperature=24.0, fan_mode=high          |
| 3    | `climate.set_fan_mode` `fan_mode: auto`                     | state=cool, temperature=24.0, fan_mode=auto          |
| 4    | `climate.turn_off`                                          | state=off,  temperature=24.0, fan_mode=auto          |

All writes surface through the next coordinator refresh (poll interval 30 s).

## 4. Kill-Restore — blackhole route on host, 45 s window

```
22:32:49  ip route add blackhole 192.168.2.20        # kill
22:33:15  coordinator: "Modbus Error: No response received after 3 retries"
22:33:32  mid-outage probe:  climate.nei_ji_1 = unavailable
                             sensor idus_online   = unavailable
22:33:34  ip route del blackhole 192.168.2.20        # restore
22:34:04  post-outage:       climate.nei_ji_1 = off (setpoint 24, fan auto preserved)
                             sensor idus_online   = 64
                             sensor idu_total     = 64
```

Recovery is fully automatic — no HA restart required.

## 5. Follow-up

`homeassistant.helpers.frame` deprecation warning during first setup:

> Detected that custom integration 'zhijingling_vrv' calls `device_registry.async_get_or_create` referencing a non existing `via_device` ('zhijingling_vrv', '<entry_id>_gateway'). This will stop working in Home Assistant 2025.12.0.

The IDU climate/sensor entities point `via_device` at a gateway device that is never explicitly registered. Track separately — non-blocking for 0.1.0 but must be fixed before HA 2025.12.

## Verdict

Task 10 acceptance criteria met: config flow succeeds against live gateway, entities appear, write path drives all four services and state persists, network kill triggers `unavailable`, restore recovers cleanly.
