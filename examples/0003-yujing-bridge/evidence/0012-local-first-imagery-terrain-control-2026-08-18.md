# Case 0003 — Local-first imagery / terrain control evidence

日期：2026-08-18 Asia/Taipei

## 架構決策

Case 0003 後續 REAL business execution 不再以 GitHub Actions 為 canonical boundary。最新版採：

`OpenWorker local durable jobs -> go-tool gtr-local-exec -> owning repo local entrypoint -> bound workspace physical artifacts`

GitHub workflow 僅保留 CI / fallback / bootstrap / evidence transport。

## 已完成程式層

### Imagery

- `terrain.streetview.acquire`：go-tool localexec handler 已存在，固定讀 accepted `geo/geolocation.json`，在 assigned host 直接產生 0/90/180/270 四向實體 PNG。
- `terrain.orthophoto.acquire`：go-tool localexec handler 已存在，直接呼叫 Terrain `terrain-orthophoto-acquire`，產生 bounded NLSC PHOTO2 mosaic + evidence。
- OpenWorker：`scripts/case0003_local_imagery_parallel.ps1` 一次提交兩個 durable jobs，使用不同 locks，可由不同 local agent slots 並行。

### Terrain AOI

2026-08-18 新增：

- Terrain_To_DXF `94c84762c9b19adb840062bc03e6541d0f2ab596`：`scripts/terrain_aoi_local.ps1`
  - assigned-host fail-closed
  - accepted geolocation only
  - canonical `D:\TaiwanDTM\catalog\dtm_catalog.sqlite`
  - local GDAL discovery
  - local `terrain-workbench` build/start
  - `/api/terrain/build` REAL call
  - physical 10-artifact validation + SHA256 manifest
- go-tool-runtime `f720acdba979e6cd8f72dfbf9fe179ad49760140`：register `terrain.aoi.build` local handler
- go-tool-runtime `aa31edb4ab28403a6e2dfff89383df78aa98971c`：Terrain AOI localexec tests
- OpenWorker `c5a479336e69ef53082f60050fb03e7f273dbf4e`：`scripts/case0003_local_terrain_aoi.ps1` durable job submitter

## REAL acceptance 尚未宣稱

本對話執行環境無法直接連線 UL7 的 `http://127.0.0.1:8787`，因此本文件只記錄程式與 contract 已 localize；不得宣稱 UL7 REAL jobs 已執行或 artifacts 已重新 accepted。

下一次在 UL7 local controller 可用時，canonical sequence：

1. 查 `/v1/node/status`、`/v1/cluster/agents`。
2. 若 queue 阻塞，使用 OpenWorker 正式 one-call queue drain，不手動逐筆取消。
3. 執行 `scripts/case0003_local_imagery_parallel.ps1`。
4. 觀察 Street View + Orthophoto 兩 jobs 真正並行並完成。
5. 人眼 / semantic QC 實體 PNG / JPG，不接受只有 bytes/hash。
6. 確認 DTM catalog 存在；執行 `scripts/case0003_local_terrain_aoi.ps1`。
7. 驗證 terrain-context/grid/DXF/heightmap/OBJ/scene/SceneX handoff 等實體成果。
8. 全部 PASS 才更新 STATUS acceptance，接 consumer -> Blender -> SceneX -> OS delivery。
