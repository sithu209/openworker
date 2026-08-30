# 0002 — 最新 go-tool capability discovery / Operator contract 閉環

## 1. Step 目的與 canonical input

本 Step 依案例規則，不直接呼叫 Terrain / Street View repo script，而是先用最新版 go-tool-runtime 發現 canonical capability、schema、readiness，再由 go-tool formal dispatch 到 owning repo 的 self-hosted Operator Action。

Canonical user input：

- `location_text = 臺南市玉井橋`
- `delivery_case = 0003`

System binding：

- assigned host：`DESKTOP-UL7V2VV`
- canonical workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- case mirror：`D:\AI-Example\0003`

`assigned_host` 不是使用者輸入，而是 OpenWorker persisted JobBinding / execution governance 傳給 Operator 的系統約束。

## 2. Latest-design audit

### 2.1 go-tool-runtime

已確認最新版正式設計具備：

- capability registry
- canonical input schema
- execution readiness
- credential auto bootstrap
- GitHub Actions `workflow_dispatch` provider
- stable execution id `<capability_id>:<workflow_run_id>`
- run / jobs / runner / artifacts / cancel query
- queue preflight / evidence contract

Action credential priority：

`local shared go-tool credential DB → GitHub App → token env`

shared DB：

`C:\ProgramData\go-tool-runtime\runtime.db`

因此 Case workflow 不應直接跨 private repo checkout 工具。

### 2.2 Terrain_To_DXF

最新版 Street View / Geo Reality 已存在於 Go capability layer：

- Google Street View metadata
- bounded snapshot
- panorama reference
- route scan
- geo-context/v1
- Blender / SceneX geo-handoff
- highest-resolution policy
- master tile acquisition / checksum evidence
- native panorama stitch

但 audit 時 go-tool registry 只正式暴露 `terrain.dxf.generate`，而 Street View Workbench 仍以 lat/lng 為核心輸入，沒有「使用者地點文字 → 正式 geolocation → Street View Operator」的完整 AI-facing contract。

## 3. 本 Step 暴露的正式缺口

### G-0003-005 — owning capability exists but AI-facing Operator contract incomplete

缺口包含：

1. `臺南市玉井橋` 這種 location text 沒有 canonical geocoding capability。
2. Street View API 存在，但沒有 typed `workflow_dispatch` Operator workflow。
3. go-tool registry 沒有 geolocation / Street View acquisition entries。
4. 初版新 Operator 若只使用共享 `ai-ci`，不能保證 Case 0003 consequential work 固定在 UL7。

這些都屬正式 integration gap，不能靠案例寫死 lat/lng 或直接呼叫 Workbench API 繞過。

## 4. Terrain_To_DXF owning-repo repair

### 4.1 Geocoding provider

新增：

- `internal/geocode/google.go`
- commit `9b18fb8751fc665fc65dcde9bf79ae63b0cf4936`

契約：

`location_text → Google geocoding → normalized_name / place_id / lat / lng / types / provider status / fetched_at / redacted URL evidence`

credential 仍只從 `GOOGLE_MAPS_API_KEY` 取得，不允許模型 request 攜帶 key。

### 4.2 Geocode CLI

新增：

- `cmd/terrain-geocode/main.go`
- commit `207b0326e5365a3e55cd1f40395ebab503e27803`

正式 input 是 location text，不接受案例偷偷寫死的玉井橋座標。

### 4.3 Street View location-text acquisition CLI

新增：

- `cmd/terrain-streetview-acquire/main.go`
- commit `5720e05a59003f3f78c862ad121f8757eb5e825b`

流程：

`location_text → geocode → Street View metadata → resolved pano coordinate → 0/90/180/270 四向 640×640 fresh snapshot → SHA256 → streetview-acquisition.json`

這是第一個正式可由 Operator 使用的真實 snapshot contract；最高解析度 master panorama 仍保留給後續 Step 4 的更高品質 gate，不以四向 static snapshot 冒充 native master panorama。

### 4.4 Typed Operator workflows

新增：

- `.github/workflows/operator-geo-resolve.yml`
- initial commit `51075f53e129ffc25a6f4220a9a24313b5b7a759`
- assigned-host correction `2387f6bac45ae7a8ce964e0308a6b758d5440010`

新增：

- `.github/workflows/operator-streetview-acquire.yml`
- initial commit `9d453fad87740bc90ef1c61c9b4bcef30f56f527`
- assigned-host correction `fdf3848a76de1535a1d4d847f9d4d30db2f60ee4`

兩條 workflow 最新 accepted routing：

- generic `[self-hosted, Windows, X64]` 只作 transport；
- matrix fan-out；
- `assigned_host` 由 OpenWorker binding 傳入；
- wrong-host candidate clean skip；
- provider credential fail-closed；
- 真正產物有 path / size / mtime / SHA256 evidence。

## 5. Terrain 自身 Win11 verification

新 geocoder + acquisition CLI 已進現有 `Go CLI and Workbench - Local Auto Verification`。

最新相關 REAL gate：

- run `31921830710`
- head `5720e05a59003f3f78c862ad121f8757eb5e825b`
- status：`completed`
- conclusion：`success`

該 gate 驗證 current Go code / tests / build 沒有破壞 Terrain mainline；但它不是 Google provider REAL acquisition，所以不能代替後續正式 Operator run。

## 6. go-tool registry repair

初次正式註冊：

- `terrain.geo.resolve`
- `terrain.streetview.acquire`
- commit `bdde9637207953360a8da7b25881b3656b90fc30`

後續發現共享 runner labels 不能保證 Case0003 host binding，因此 contract 再補：

- required system input `assigned_host`
- runner labels 降為 transport `[self-hosted, Windows, X64]`
- Operator workflow 內做 fail-closed host gate
- commit `7d5e0d51aaa8703b7f6a45061d6e1e992f850314`

這個修正是通用能力，不是 `0003` 特例；未來其他 OpenWorker job 也可以用自己的 persisted assigned host。

## 7. go-tool Case0003 formal dispatch harness

新增：

- `cmd/e2e-0003-dispatch/main.go`
- initial commit `24f4732fa69b83d59b38c221d89edf65145ee7de`
- assigned-host correction `e94aa054b37fb2a324c873ff760dd89667cf0f60`

Harness 只在 `DESKTOP-UL7V2VV` 執行，並依序保存：

1. go-tool health
2. capability list
3. `terrain.geo.resolve` detail/schema
4. `terrain.streetview.acquire` detail/schema
5. execution readiness / credential source
6. geolocation dispatch request / receipt
7. geolocation run/jobs polling / artifacts
8. Street View dispatch request / receipt
9. Street View run/jobs polling / artifacts
10. final result

正式 dispatch input：

- user：`location_text = 臺南市玉井橋`
- system：`assigned_host = DESKTOP-UL7V2VV`
- Street View bounded option：`radius_m = 100`

不包含 hard-coded lat/lng。

## 8. UL7 self-hosted formal E2E workflow

新增：

- `.github/workflows/operator-e2e-0003-yujing-bridge.yml`
- initial commit `8c86549d321c5fe97b729f62b356d3dae27e2828`
- latest-run-only concurrency correction `b04e81b32012f1a288b06f5d1b00f766db0dfcf8`

transport：16 個 generic Windows/X64 candidates；只允許 `COMPUTERNAME == DESKTOP-UL7V2VV` 的 candidate 取得 host-local lock 後執行 harness，其餘 clean skip。

歷史 run：

- run `31921927544` — 舊 contract（assigned_host correction 前）；由後續 latest-run-only policy 取代，不應作 accepted result。

目前正式 run：

- run `31922043708`
- head `b04e81b32012f1a288b06f5d1b00f766db0dfcf8`
- run number `3`
- 當前狀態：transport candidates queued，等待 self-hosted runner 接單
- 尚未取得 UL7 selected business job，因此本 Step 尚不能標 PASS。

## 9. Current verdict

- latest-design audit：PASS
- geolocation owning capability：IMPLEMENTED
- Street View AI-facing Operator：IMPLEMENTED
- go-tool capability registry：IMPLEMENTED
- persisted-host propagation：IMPLEMENTED
- Terrain compile/test Win11 gate：PASS
- Case0003 formal UL7 go-tool dispatch：`IN PROGRESS / WAITING FOR SELECTED UL7 JOB`
- REAL geolocation artifact：PENDING
- REAL Street View artifact：PENDING

## 10. Accepted procedure so far

後續不得：

- Case workflow direct-checkout private tool repos；
- hard-code 玉井橋座標；
- 只靠 `ai-ci` 假設是指定機器；
- 用 unit/mock success 冒充 Google REAL provider success。

Accepted path：

`OpenWorker persisted binding → UL7 go-tool → capability discovery/schema/readiness → assigned_host system binding → go-tool formal dispatch → Terrain operator host gate → REAL provider → physical artifact/evidence → go-tool run/jobs/artifacts query → OpenWorker ledger/manual`

## 11. Next

追 run `31922043708` 到 UL7 selected candidate。若 fail：保存 provider / credential / workflow / capability error，修真正 owner後從同一 Step 重跑。若 geolocation PASS：記錄 normalized location / lat/lng / provider evidence；若 Street View PASS：記錄四向 images / metadata / hashes，接著進 native master panorama / terrain AOI Step。
