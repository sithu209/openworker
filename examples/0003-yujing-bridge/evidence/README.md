# 0003 臺南市玉井橋 — Evidence Index

本目錄只保存**證據索引與驗收規則**；大型街景影像、terrain data、`.blend`、SceneX exchange artifact、SceneX runtime capture 與成果網站 physical files 保存在正式 execution workspace / OS delivery workspace，不複製大型二進位成果進 Git。

## Canonical input

- location_text：`臺南市玉井橋`
- delivery_case：`0003`
- assigned host shorthand：`UL7`
- assigned Windows computer：`DESKTOP-UL7V2VV`
- canonical delivery entry：`delivery/website/index.html`

## 必須收集的 evidence

1. 工具版本 provenance：OpenWorker / go-tool / AI-Engineering-OS / 地理街景工具 / Blender integration / SceneX 實際使用 SHA。
2. go-tool health / capabilities / capability detail / readiness / dispatch response。
3. execution id / target run id / job id / runner identity / Windows `COMPUTERNAME`。
4. UL7 routing proof：只有 `DESKTOP-UL7V2VV` 執行 consequential work；其他 runner clean skip。
5. geocoding result：標準化地名、latitude、longitude、來源、解析時間、候選排除證據。
6. street-view provenance：pano 或等價 identity、heading / pitch / FOV、capture/source metadata。
7. accepted street-view physical files：path / size / mtime / SHA256。
8. terrain/AOI：bbox/radius、coordinate reference、scale、north、來源資料與 physical file hashes。
9. Blender scene evidence：`.blend` path / size / mtime / SHA256、scene units、origin、north、主要 objects、preview render。
10. Blender → SceneX transfer artifact：format / path / size / mtime / SHA256。
11. SceneX import identity：scene/project/runtime identity 與 imported artifact correlation。
12. SceneX runtime evidence：橋頭、橋面、周邊地形至少三個新鮮視角或等價 capture。
13. OS Artifact Registry：accepted artifact identities、hashes 與 case/execution correlation。
14. Delivery Revision：revision identity、納入的 artifacts、QC / delivery metadata。
15. 成果網站：`delivery/website/index.html` path / size / mtime / SHA256，以及所有必要靜態資源 manifest。
16. website verification：頁面可打開、無 placeholder / broken links、內容可辨識為臺南市玉井橋案例，且引用成果與 Registry / Delivery Revision 一致。
17. blocker evidence：任何既有工具無法完成步驟時的正式輸入、輸出、錯誤、owning repo、run/job identity。

## REAL 驗收規則

- workflow success 本身不是成果。
- geocoding 成功但位置錯誤，不算成功。
- 網頁搜尋圖片、無來源截圖、示意地形不能冒充真實資料。
- Blender CLI exit code 0 但沒有 physical `.blend` / scene artifact，不算成功。
- SceneX 只成功解析檔案格式但沒有實際 runtime 場景，不算成功。
- SceneX 打開空白 editor、預設場景或無法辨識為玉井橋的畫面，不算成功。
- SceneX REAL browse PASS 但沒有 OS Artifact Registry / Delivery Revision，不算完成。
- 有 Registry / Revision 但沒有 physical `delivery/website/index.html`，不算完成。
- 成果網站若只有 placeholder、壞連結、無法追溯 artifact、或不是本次 execution 的新鮮產物，不算完成。
- 舊 artifact、mtime 不新鮮、無 execution correlation，不算成功。
- accepted artifact 需要有 SHA256 與 provenance chain。
- 每次重跑都記錄當下最新工具 SHA；SHA 是 provenance，不是 compatibility pin。

## 成果網站最低 evidence

成果網站至少應能展示或索引：

- 臺南市玉井橋 canonical location；
- street-view / terrain provenance 摘要；
- Blender preview；
- SceneX 三個以上 accepted runtime captures；
- `.blend` / SceneX exchange artifact identity；
- QC 結果；
- Artifact Registry identity；
- Delivery Revision identity；
- execution / job / runner / tool SHAs。

## 最終證據鏈

完成時應可從成果網站反查整條鏈：

`delivery/website/index.html → Delivery Revision → Artifact Registry → SceneX capture/scene → imported 3D artifact SHA → accepted Blender scene SHA → terrain/street-view source SHA → canonical 玉井橋 geolocation → case execution/job → UL7 runner → tool SHAs`

最終 accepted evidence 必須由 `STATUS.md` 指向，且 **成果網站是案例的正式交付面**。
