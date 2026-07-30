# ZhiJingLing VRV Integration — UI Screenshots / 介面截圖

Live captures from a production Home Assistant OS instance running the
`zhijingling_vrv` custom integration against a real 智精靈 gateway at
`192.168.2.20`, with 12 indoor units enrolled.

從實際運作的 Home Assistant OS 擷取，對接部署於 `192.168.2.20` 的
智精靈閘道，共 12 台室內機。

| # | File | Screen / 畫面 | What it shows / 說明 |
|---|------|---------------|-----------------------|
| 01 | `01-integration-page.png` | Integration page — `Settings ▸ Devices & services ▸ ZhiJingLing VRV` | Integration overview: version 0.1.0, 65 devices, 66 entities, single config entry `智精靈閘道 (192.168.2.20)` expanded to show 內機 1–8. Version, custom-integration badge, and device/entity counts confirm a healthy setup.<br>整合總覽頁：版本 0.1.0，65 個裝置、66 個實體，單一設定項目 `智精靈閘道 (192.168.2.20)` 展開顯示內機 1–8。 |
| 02 | `02-integrations-list-filtered.png` | Integrations dashboard filtered by `vrv` | Confirms discovery from the integrations browser and the placeholder brand icon fallback. Useful when writing installation docs.<br>整合瀏覽器篩選 `vrv` 結果，驗證 HACS 品牌圖示回退機制。 |
| 03 | `03-devices-list.png` | Devices list filtered by domain `zhijingling_vrv` | All 12 IDUs listed as `內機 1`–`內機 12` with manufacturer `智精靈` and model `VRV IDU (slot N)`. Verifies device registry population from Modbus slot metadata.<br>顯示 12 台內機皆完整登錄，含製造商與型號欄位。 |
| 04 | `04-entities-filtered.png` | Entities filtered by config entry | Shows `climate.nei_ji_1` … `climate.nei_ji_6` created by the integration with enabled state and visible names. Filter uses `?config_entry=<entry_id>`.<br>依 config_entry 篩選出所有由此整合建立的實體。 |
| 05 | `05-devtools-actions.png` | Developer Tools ▸ Actions | Actions (formerly "Services") developer panel — reference for troubleshooting `climate.set_temperature`, `climate.set_hvac_mode`, `climate.set_fan_mode`.<br>Developer Tools 動作面板，可手動觸發 climate.* 服務進行除錯。 |
| 06 | `06-climate-more-info.png` | More-info dialog for `climate.nei_ji_1` | Real running state: current 48 °C, setpoint 21 °C, mode Fan only, fan Low. Demonstrates the round dial UI, fan-mode chips, and the auxiliary metadata block.<br>climate 實體的詳細資訊對話框，展現目前溫度、設定溫度、模式與風速切換介面。 |
| 07 | `07-integrations-dashboard.png` | Integrations dashboard with discovered devices | Illustrates neighbouring integrations (MQTT, EMQX, HACS, ESPHome Builder, DHCP) coexisting on the same HA instance. Useful for new-user "does this fit my HA?" context.<br>整合面板總覽，同時展示 MQTT / EMQX / HACS / ESPHome 等鄰近整合。 |
| 08 | `08-single-device-idu-1.png` | Single device page for `內機 1` | Device Info panel (via Modbus slot 0), Controls (climate widget), and Activity log. Reveals the identifiers, manufacturer, and firmware surface areas that `device_info` exposes.<br>單一內機的裝置頁，含 Device Info、Controls、Activity Log 三大區塊。 |
| 09 | `09-lovelace-viewport.png` | Lovelace overview dashboard | Shows the `climate.nei_ji_1` card in a real user dashboard alongside lighting, cameras, calendars, and covers — proving the integration's climate entity renders and controls cleanly in Lovelace.<br>Lovelace 面板實際使用畫面，內機 1 的 climate 卡片與其他實體並存。 |

## Capture method / 擷取方式

All shots were taken via Playwright headless Chromium (viewport 1440×900,
locale `zh-TW`) with a minted access token injected into
`localStorage.hassTokens`, so they reflect the exact rendering an operator sees.

所有截圖均以無頭 Chromium (視窗 1440×900、locale `zh-TW`) 執行，將 HA
存取權杖注入 `localStorage.hassTokens`，忠實呈現實際操作畫面。

## Notes / 備註

- Screenshot 01 shows the "icon not available" placeholder because the HA
  instance has not yet reloaded the community brand assets since the recent
  `home-assistant/brands` submission.
- 「icon not available」佔位圖示是因 HA 尚未重新載入品牌資源；下次重啟後即
  會顯示 `custom_components/zhijingling_vrv/brand/icon.png`。
