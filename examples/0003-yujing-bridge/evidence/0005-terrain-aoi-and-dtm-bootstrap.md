# 0005 — Terrain AOI / Taiwan DTM bootstrap

更新時間：2026-08-16 Asia/Taipei

狀態：`IMPLEMENTING / FULL DTM BOOTSTRAP IN PROGRESS`

## 1. Step purpose

在已接受的 `臺南市玉井橋` geolocation 與四向 Street View 基礎上，建立真實 terrain/elevation AOI，輸出 canonical Terrain artifacts，後續交給既有 Blender / SceneX 正式路徑。

本步驟不得使用假 DEM、手工座標或案例專用地形。

## 2. Latest-design audit

`Terrain_To_DXF` 最新正式架構已具有：

- Taiwan 20m DTM source contract
- local catalog / SQLite + RTree query contract
- terrain-context/v1
- one-click Terrain build
- grid / DXF / heightmap / OBJ mesh
- terrain scene / SceneX handoff
- REAL Blender execution handoff

因此 Case 0003 不另造 terrain 或 Blender 系統，只補 workspace/operator/orchestration 缺口。

## 3. Formal terrain.aoi.build operator

新增：

- `Terrain_To_DXF/.github/workflows/operator-terrain-aoi-build.yml`
- commit `da41d2c24563fbcb50599f99b1dad9c661e16d2a`

正式能力：

- input 只接受 OpenWorker persisted workspace/host/project + OS-owned AOI profile
- 從 `workspace\geo\geolocation.json` 讀 accepted geolocation
- bounded AOI
- canonical local Taiwan DTM catalog
- one-click Terrain build
- fail-closed 驗證實體 terrain-context / grid / DXF / heightmap / OBJ / scene / SceneX handoff
- 實體檔逐檔 SHA256 evidence

`go-tool-runtime` 已註冊：

- capability `terrain.aoi.build`
- commit `d99e8d22...`

AI-Engineering-OS Case 0003 driver 已改為 resume-aware：

- accepted geo / Street View 只重新驗實體檔與 SHA，不重做
- 只 dispatch 下一個 `terrain.aoi.build`
- commit `0ed3a893...`

## 4. First REAL terrain AOI attempt

Outer OS run：

- `31923998028`

Terrain target run：

- `31924030088`
- selected UL7 job：`95108616144`
- runner：`DESKTOP-UL7V2VV-R006`
- machine：`DESKTOP-UL7V2VV`

Result：`FAIL-CLOSED`

真正 blocker：

```text
canonical terrain catalog missing:
D:\TaiwanDTM\catalog\dtm_catalog.sqlite
```

結論：

- 不是 geolocation 錯誤
- 不是 Street View 錯誤
- 不是 Terrain build algorithm 錯誤
- UL7 尚未 materialize canonical Taiwan DTM local database

## 5. User decision

使用者明確決定：

> 本機沒有 DEM 就完整重新下載

因此 repair policy 改為：

- 不只下載玉井橋 AOI
- 在 UL7 完整建立共享 `D:\TaiwanDTM`
- 後續案例直接重用相同官方資料庫
- 不把大型 DEM 放 GitHub artifact / Git

## 6. Official dataset first-level index gap

Terrain 現有下載器最初只看到 data.gov.tw dataset `176927` 的直接 resource。

REAL run `31924246620` / UL7 job `95109180275` 證明：

- 第一層只有 1 個 CSV
- 大小約 5.42 KB
- SHA256 `5f6e853ccb044d7b76dbe95f4a8a3890f9d5f0613105e0428743f36658aa8869`
- 這不是 DEM 本體，而是二級資源索引

另補 UTF-8 Windows runner 修復：

- `003100641feb9b627d8ab4d9ef9042ed0626440f`

## 7. Official CSV index REAL inspection

Probe run：

- `31924300126`
- UL7 job：`95109313914`
- runner：`DESKTOP-UL7V2VV-R006`

CSV 欄位：

```text
圖資名稱,製作說明,圖資類型,圖資坐標系統,年度,連結網址
```

索引內確認存在正式 TGOS ZIP：

- schema header
- 臺南市
- 臺東縣
- 臺北市
- 臺中市
- 彰化縣
- 嘉義縣 / 嘉義市
- 新竹縣 / 新竹市
- 新北市
- 雲林縣
- 基隆市
- 高雄市
- 桃園市
- 苗栗縣
- 屏東縣
- 南投縣
- 花蓮縣
- 宜蘭縣
- 澎湖縣
- 金門縣
- 不分幅澎湖
- 不分幅金門
- 不分幅全台 20m DEM

因此既有 downloader 的產品缺口是：

`data.gov.tw API resource → CSV index` 有做，`CSV index → 真實 TGOS ZIP resources` 沒有做。

## 8. Generic owning-repo repair

新增遞迴 downloader：

- `tools/download_taiwan_dtm_recursive.py`
- commit `a6adfb387bf9ac8a5ce81fc5725d55e1dda63c2c`

功能：

1. 使用既有 resumable downloader 抓第一層官方 resource。
2. 掃描小型 CSV/TXT/JSON/TSV index。
3. 抽取 HTTP(S) download URLs。
4. 中文 URL path percent-encode。
5. 將新 URL 餵回既有 downloader。
6. 重複直到沒有新 resource。
7. 保留 existing SQLite resumable transport state / SHA256。

Full bootstrap workflow 已切到 recursive downloader：

- commit `48e104fcc75fc0c64ce91a843cc39e781468e144`

## 9. Current REAL full download

Run：

- `31924347661`
- workflow：`Taiwan DTM Full Bootstrap`
- selected business job：`95109431249`
- runner：`DESKTOP-UL7V2VV-R006`
- machine：`DESKTOP-UL7V2VV`

目前已通過：

- exact UL7 routing
- checkout latest Terrain
- reset stale spatial catalog only
- preserve resumable raw transport state

目前執行：

```text
Recursively expand official index and fully download all resources
```

下載根目錄：

```text
D:\TaiwanDTM
```

資料策略：

```text
catalog/   official metadata + resumable download DB + final spatial catalog
raw/       official ZIP / resource files
extracted/ safely extracted resources
normalized/ normalized terrain products
cog/       canonical raster/COG products
```

## 10. Acceptance rule

「下載完成」不等於 Terrain AOI 完成。

本步最終 acceptance 必須再完成：

1. 全量官方 ZIP 實體下載 + SHA256
2. safe extract
3. normalize / raster or COG materialization
4. `D:\TaiwanDTM\catalog\dtm_catalog.sqlite`
5. `terrain_tiles + RTree` spatial records
6. 玉井橋 AOI query 至少找到一筆 `ready=true` tile
7. 重跑同一 `terrain.aoi.build`
8. 實體產出 terrain-context/grid/DXF/heightmap/OBJ/scene/SceneX handoff
9. OpenWorker accepted event + provenance

未達上述條件前，本 Step 保持 `IMPLEMENTING`。
