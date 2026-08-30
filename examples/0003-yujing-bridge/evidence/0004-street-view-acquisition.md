# 0004 — Street View Browser Screenshot acquisition

## 1. 本 Step 目的

Case 0003 的 Street View 正式路徑採用 `Terrain_To_DXF` 最新 Browser URL / Headless Render 設計，不再把 Google Static Street View API snapshot 當成本案例的街景視覺取得方式。

Canonical user input 仍只有：

- `location_text = 臺南市玉井橋`
- `delivery_case = 0003`

System binding：

- assigned host：`DESKTOP-UL7V2VV`
- canonical workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- case mirror：`D:\AI-Example\0003`

座標必須由前一步正式 `terrain.geo.resolve` 產生；案例、LLM 與 Street View workflow 都不得硬寫玉井橋 lat/lng。

## 2. Latest-design audit

`Terrain_To_DXF/docs/16-streetview-browser-url-mode.zh-TW.md` 已定義 GEO-STREETVIEW-07：

```text
Browser URL Mode
  → official Google Maps pano URL
Headless Render Mode
  → controlled Chrome/Edge
  → bounded viewport / timeout
  → browser viewport screenshot
  → bytes / SHA256 / render evidence
```

正式 URL contract：

```text
https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=<lat>,<lng>
```

Headless Render 的安全邊界：

- 只允許 `www.google.com/maps/@` pano URL；
- Chrome/Edge 由工具自行 discovery，不接受模型指定 arbitrary executable；
- 不解析 undocumented XHR / tile URL；
- 不下載、拼接或攔截 panorama tiles；
- screenshot 只是 browser viewport render，不能冒充 Static Street View API 原始影像或工程幾何真值。

最新版程式已存在：

- `internal/streetview/browser_url.go`
- `internal/streetview/headless.go`

其中 headless renderer 已實作 browser discovery、allowlist、viewport/timeout bounds、PNG artifact、bytes、SHA256、render timestamp。

## 3. 本案例暴露的缺口

先前新增的 `terrain.streetview.acquire` Operator 錯接到較舊 Static API acquisition CLI：

```text
location_text
→ Google geocode
→ Street View metadata
→ Static API 四向 snapshots
```

而且 workflow 要求 repository secret `GOOGLE_MAPS_API_KEY`。

這與 Case 0003 要使用的最新 Headless Render 設計不一致。此問題不是核心 Street View renderer 缺失，而是「新版核心能力已存在，但 AI-facing Operator 沒接到最新版 contract」。

因此舊的 Static snapshot Operator path 在 Case 0003 中標記為 **SUPERSEDED**，不得作為 accepted Street View visual acquisition procedure。

## 4. Owning-repo repair

### 4.1 Headless Render CLI

新增：

- `cmd/terrain-streetview-render/main.go`
- commit `7559c40faa4687e09ea39c93114b02f1dafbb3ec`

CLI 依原 GEO-STREETVIEW-07D 設計：

```text
lat/lng + heading/pitch/fov
→ BuildBrowserURL
→ DiscoverChromium
→ RenderBrowserScreenshot
→ PNG + JSON evidence
```

限制：

- viewport：640×480 ~ 1920×1080；
- timeout：1 ~ 60 秒；
- output 必須為 PNG；
- URL 必須通過 Google Maps pano allowlist。

### 4.2 Self-hosted compile/test gate

Terrain Win11 local Action：

- run `31922461910`
- head `7559c40faa4687e09ea39c93114b02f1dafbb3ec`
- conclusion：`SUCCESS`

因此新 `terrain-streetview-render` 已通過既有 Go test / vet / build self-hosted gate；這個 gate 只驗證程式與 build，不能代替玉井橋 REAL screenshot run。

### 4.3 Street View Operator 改接 Headless Render

Operator：

- `.github/workflows/operator-streetview-acquire.yml`
- initial screenshot switch commit `3e35b6e068f1d65feb81cda6d120f0c8864df64c`
- workspace-backed correction commit `2752db1d596375dd06e067dcb58597926348385f`

Accepted execution：

```text
OpenWorker bound workspace
→ geo/geolocation.json
→ read accepted lat/lng
→ Chrome/Edge headless
→ heading 0° screenshot 1920×1080
→ heading 90° screenshot 1920×1080
→ heading 180° screenshot 1920×1080
→ heading 270° screenshot 1920×1080
→ per-image SHA256
→ streetview-browser-screenshots.json
→ workspace/streetview/browser/*
```

Street View screenshot Step 本身不再依賴 `GOOGLE_MAPS_API_KEY`。

### 4.4 Geolocation / workspace handoff correction

`terrain.geo.resolve` 仍負責把使用者文字解析成正式 geolocation。新 Operator 原本把 repo secret 空值寫進 `GOOGLE_MAPS_API_KEY`，會覆蓋 self-hosted runner 既有 machine-local environment credential。

修正：

- commit `e56e6beeb1e2a717ed030c87a9202ae7d3b79a6a`
- repository secret 若存在則優先；否則保留 machine-local `GOOGLE_MAPS_API_KEY`；兩者皆無才 fail-closed。

之後又補正式 workspace materialization：

- commit `1b6d4183fc2937439bc70f161a0f0ee7a872ea7c`

成功 geolocation 必須 materialize：

```text
D:\AI-Work\jobs\0003-YUJING-BRIDGE\geo\geolocation.json
```

Street View Operator 只讀這個 accepted state，不由案例重新解析或硬寫座標。

### 4.5 REAL geo rerun 與 credential gap

正式 go-tool Case0003 run：

- parent run `31922591331`
- selected UL7 parent job `95104797958`
- target geolocation run `31922624858`
- selected UL7 geo job `95104881218`
- runner：`DESKTOP-UL7V2VV-R006`
- computer：`DESKTOP-UL7V2VV`
- workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`

已確認：

1. UL7 host gate PASS；
2. Terrain repo checkout PASS；
3. Go setup PASS；
4. `GOOGLE_MAPS_API_KEY` repository secret 為空；
5. self-hosted runner service environment 亦沒有 `GOOGLE_MAPS_API_KEY`；
6. geo readiness 因此 fail-closed；
7. 尚未產出 accepted `geo/geolocation.json`；
8. Street View screenshot target 因前置 geo 未成功，尚未 dispatch。

這次失敗證明問題已縮小為 geolocation provider credential，而不是 UL7、go-tool dispatch、workspace、Street View headless renderer 或 browser routing。

### 4.6 對齊既有 build-time demo key injection 設計

Terrain 既有 commit：

- `de8a7aa82d1b6729fc62cb5876365820a1173e79`
- title：`feat(streetview): support build-time demo key injection`

其設計規則：

- `BuildGoogleMapsAPIKey` 在 source control 永遠保持空值；
- trusted local build 可用 `-ldflags -X` 注入 disposable/demo key；
- runtime environment variable 優先於 build-time injected value；
- key 不得出現在 evidence。

Case 0003 已把 geocoder 對齊同一模式：

- commit `5cf75e5e8f1c8fb0cb9bec4c8f17258c14c443ea`
- `internal/geocode.BuildGoogleMapsAPIKey`
- environment first；build-time injection second；source control empty。

使用者已提供 Google Maps demo key 作為本案例可用 credential；**該 key 不寫進 Git 手冊、workflow、evidence 或任何 commit**，文檔只記錄「demo key supplied out-of-band」。

### 4.7 Provider-neutral fallback gap

因目前 GitHub connector 無 repository-secret write 能力，而 runner service 也沒有 Google key，為避免 Case 0003 被 credential plumbing 阻塞，Terrain 同步補 explicit provider selection：

- `055d4aa06b834fad1d7772cf935193d410bdf373` — bounded Nominatim resolver
- `7fca1dfb9acbc6751d6acc5ddc6b8eaada729899` — canonical Result 增加 attribution
- `790ba071ee0edd5e5d19cddafc7d304685dfbd6a` — explicit `TERRAIN_GEOCODER` selector
- `e6243bc50cecb66c883594621d83a80e2d3cebd1` — `terrain-geocode` CLI 接 provider selector
- `b82c63f14d88b214f1671422882ef4caedfe9348` — Operator：Google credential available → Google；否則 explicit bounded Nominatim fallback

Nominatim 僅做 location lookup，不用於 Street View imagery。Street View 視覺證據仍固定使用 Google Maps Browser URL + headless screenshot。

## 5. go-tool contract repair

`go-tool-runtime/config.yaml` 已把 `terrain.streetview.acquire` 改成正式 Headless Browser Screenshot contract：

- commit `5bdf57fcfe27ca06863d0996d03a1a2079e6bdc2`
- 移除舊 `radius_m` / Static API 描述；
- required system inputs：`workspace_root`、`assigned_host`；
- artifact pattern：`terrain-streetview-browser-operator-*`。

`terrain.geo.resolve` 同步增加 `workspace_root`，讓 accepted geolocation 進 OpenWorker-bound workspace。

Case 0003 go-tool E2E harness 亦更新：

- commit `9e70e661b69ddd6678bec7b318100f88c1def701`
- formal workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- geo success 後驗證 workspace `geo/geolocation.json`；
- Street View dispatch 不傳 lat/lng，只傳 workspace + assigned host；
- screenshot success 後驗證 workspace manifest 包含 0/90/180/270 四個 heading。

## 6. REAL execution state

正式 parent run：

- run `31922591331`
- head `9e70e661b69ddd6678bec7b318100f88c1def701`
- workflow：`Operator E2E 0003 Yujing Bridge`

第一次 selected UL7 attempt 已走到 target geo run `31922624858`，並因 Google credential absence 正確 fail-closed；完整 job log 已確認 host/workspace/checkout/go setup 均正常。

在 geocoder provider fallback 修復後，已對 parent run 執行 failed-jobs rerun；新 attempt 正在等待真正 UL7 selected candidate。非 UL7 candidates 已大量 clean-skip success，不能當 business PASS。

因此目前仍不能把 REAL 玉井橋 Street View 標成 PASS。

## 7. Accepted procedure

本案例後續 Street View 不得再：

- 把 Static Street View API snapshot 當本案例正式視覺取得路徑；
- 在案例碼寫死玉井橋 lat/lng；
- 讓 Street View Operator 自己重做 geocode；
- 從任意 URL / arbitrary browser executable 截圖；
- 把 screenshot 宣稱成 survey / terrain geometry 真值；
- 把 demo key 明文寫進 Git、workflow 或 evidence。

正式程序固定為：

```text
OpenWorker persisted JobBinding
→ go-tool terrain.geo.resolve
→ UL7 local Action
→ Google geocoder when configured; otherwise explicit bounded Nominatim lookup
→ workspace/geo/geolocation.json
→ go-tool terrain.streetview.acquire
→ UL7 local Action
→ official Google Maps pano Browser URL
→ bounded Chrome/Edge headless screenshot
→ four 1920×1080 PNGs + SHA256 + manifest/evidence
→ workspace/streetview/browser
→ AI Vision / Blender visual reference only
```

Terrain / DEM / DTM 仍是 geometry/elevation 真值。

## 8. 每一步即時記錄規則

從本次修正起，Case 0003 每個 consequential step 必須在進入下一步前回寫 evidence：

1. local Action run id；
2. selected job id；
3. runner name / COMPUTERNAME；
4. tool/repo SHA；
5. canonical input；
6. workspace path；
7. readiness/provider/credential source（不含 secret）；
8. physical artifact path / size / mtime / SHA256；
9. failure root cause；
10. owning repo repair commit；
11. same-Step rerun id/job id；
12. accepted verdict；
13. next Step。

`queued` / wrong-host clean skip / workflow 200 / artifact-upload quota failure 都不得被誤記成 business success。

## 9. Next acceptance gate

追 parent rerun：

1. UL7 selected candidate；
2. go-tool discovery/schema/readiness；
3. `terrain.geo.resolve` target run；
4. `geo/geolocation.json` materialized；
5. `terrain.streetview.acquire` target run；
6. Chrome/Edge headless REAL render；
7. 四張非空 PNG；
8. 每張 SHA256 與 manifest 一致；
9. 把新 run/job/provider/artifact evidence 即時補入本手冊；
10. 通過後才進 Terrain AOI / Blender scene。
