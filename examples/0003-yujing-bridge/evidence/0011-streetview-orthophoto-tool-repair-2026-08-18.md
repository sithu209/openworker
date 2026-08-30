# 0011 — Case 0003 街景 / 正射影像工具缺口修復（2026-08-18）

## 結論

Case 0003 回報顯示，既有狀態曾把 Street View 寫成 accepted，但原始 evidence 同時明確記錄 REAL 玉井橋 Street View 尚不能標 PASS。2026-08-18 重新 audit 後確認兩個 owner-level 缺口：

1. `terrain.streetview.acquire` 正式走 headless browser screenshot，但黑圖 / 無可讀內容的語意驗證只存在於 master panorama stitch 路線，headless screenshot 自身只驗證檔案存在與非零 bytes，因此可能把黑 PNG 誤判為成功。
2. Case 0003 需要的「正射影像」在 `go-tool-runtime` 正式 registry 與 `Terrain_To_DXF` 主流程中沒有獨立 AI-facing capability；這不是單純 Action 失敗，而是缺少正式工具鏈。

因此本次不接受舊的 `GEO+STREETVIEW ACCEPTED` 作為最終品質結論；街景與正射影像都必須用修復後最新版重新跑同一步，產生真實 artifact 後才能 PASS。

## Street View owning repair

Owner：`liuxb99/Terrain_To_DXF`

2026-08-18 已完成：

- `027915e7e4ddf8384ab680cdb4a1f5105834fad6` — `fix(streetview): reject unreadable headless screenshots`
  - `RenderBrowserScreenshot` 在寫出 PNG 後不再只檢查 bytes。
  - PNG 必須可 decode。
  - 直接重用 Street View 可視性分析，檢查 non-black pixel ratio、luma stddev、luma range。
  - 黑圖 / 幾乎純色不可讀畫面 fail-closed，不產生成功 receipt。

- `d1c58f96e5a0a6ca3448c45af79732bf1e9af96a` — `test(streetview): reject black headless screenshots`
  - 新增黑 PNG rejection test。
  - 新增可視 PNG acceptance test。
  - 同步 headless runtime contract：`--virtual-time-budget=20000`、ANGLE + SwiftShader WebGL arguments。

此修復直接對應 Case 0003 目前正式 `terrain.streetview.acquire` 的 headless 路徑，不再只保護另一條 master panorama stitch 路徑。

## Orthophoto owning repair

官方來源採內政部國土測繪中心 NLSC WMTS：

- provider：NLSC
- layer：`PHOTO2`
- matrix set：`GoogleMapsCompatible`
- format：JPEG
- bounded case acquisition zoom：19
- acquisition policy：不得做全臺或大量 cache；Case workflow 僅允許中心 tile 周圍有限 tile 集。

Owner：`liuxb99/Terrain_To_DXF`

2026-08-18 已新增：

- `75243b7090004b10aea54c5898004dcc173b4088` — `internal/orthophoto/nlsc.go`
  - Web Mercator lat/lng → WMTS tile 計算。
  - NLSC `PHOTO2` URL builder。
  - hard bound：`radius_tiles <= 2`，單次最多 25 tiles。
  - 每 tile HTTP / JPEG decode / size / SHA256 validation。
  - tile mosaic。
  - output JPEG + complete evidence JSON + source attribution。

- `12065ba2ebeaf83ac2512111fc08518d5374a453` — bounded PHOTO2 planning tests。

- `7b4b86dc03e4895e35b8c2ae024a197986d13b5f` — `terrain-orthophoto-acquire` CLI。

- `d7c19229ea327c48c46d487d2177db89f0a16986` — `.github/workflows/operator-orthophoto-acquire.yml`
  - persisted OpenWorker workspace + assigned host contract。
  - exact `COMPUTERNAME` host gate。
  - action lock，避免同一 assigned host 重複 consequential execution。
  - 只讀 accepted `geo/geolocation.json`，案例不硬寫座標。
  - 先 `go test ./...` / `go vet ./...` / build current producer。
  - 實際輸出：`workspace/orthophoto/nlsc-photo2/orthophoto-photo2-z19.jpg`。
  - evidence：provider/layer/tile count/bytes/SHA256/runner/workspace/provenance。

## 尚未完成的 acceptance gate

上述 commit 代表 owning tool 已補缺口，**不代表 Case 0003 已完成**。必須依案例鐵律用 UL7 從原失敗 Step 重跑：

### Street View

1. 使用最新版 Terrain owner commit。
2. 由 go-tool `terrain.streetview.acquire` dispatch 到 `DESKTOP-UL7V2VV`。
3. 四向 0/90/180/270 headless screenshot 都必須通過新的 semantic visibility gate。
4. 四張 physical PNG 必須存在、非黑、SHA256 與 manifest 一致。
5. 再由視覺審查確認確實是玉井橋附近 Google Maps Street View，而不是 consent page / error page / blank canvas。

### Orthophoto

1. 將新 owner workflow 正式註冊進 go-tool capability registry（建議 id：`terrain.orthophoto.acquire`）。
2. go-tool detail/schema/readiness 必須可 discovery。
3. 由 UL7 Action 從 accepted `geo/geolocation.json` 取得玉井橋中心座標。
4. 以 NLSC `PHOTO2` zoom 19、radius_tiles=1 取得 3×3 bounded tile mosaic。
5. 實體 JPEG / evidence JSON / SHA256 必須進 canonical workspace。
6. 視覺審查必須能辨認道路、河道、橋位與周邊地物；若來源區域無有效影像或回傳 placeholder，必須 fail-closed，不得只以 HTTP 200 判 PASS。

## 下一步

先註冊 `terrain.orthophoto.acquire` 到 go-tool，然後 Case 0003 在 UL7 依序重跑：

`terrain.streetview.acquire` → `terrain.orthophoto.acquire`

兩者 REAL artifact 都通過後，再將結果餵給 Terrain consumer / Blender；在那之前不得把街景或正射影像寫成 ACCEPTED。
