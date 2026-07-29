# Woow_ha_vrv_climate_component

Home Assistant custom integration for the **ZhiJingLing (智精靈) VRV
gateway family (UACC-Bs-XX)** over Modbus TCP.

- One `climate` entity per connected indoor unit (up to 64 IDUs per gateway).
- Dynamic add: newly-connected IDUs appear automatically without reload.
- Offline IDUs remain in the entity registry as `unavailable` (delete
  manually if the IDU is physically removed).

## Install

### HACS custom repository

1. HACS → menu → *Custom repositories*
2. Add `https://github.com/WOOWTECH/Woow_ha_vrv_climate_component`,
   category *Integration*
3. Install *ZhiJingLing VRV*
4. Restart Home Assistant

### Manual

Copy `custom_components/zhijingling_vrv/` into
`<config>/custom_components/` and restart HA.

## Setup

*Settings → Devices & Services → Add Integration → ZhiJingLing VRV*.
Enter the gateway IP (Modbus TCP must be enabled on the gateway web UI —
菜单 → 网络 → 网络协议 = `MODBUS-TCP`).

## Design

See [`docs/plans/2026-07-29-zhijingling-vrv-integration-design.md`](docs/plans/2026-07-29-zhijingling-vrv-integration-design.md).

## License

MIT. See [`LICENSE`](LICENSE).
