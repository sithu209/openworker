# Case 0003 玉井橋 — SceneX 語義修復與 BAT 人工作品驗收

日期：2026-08-18（Asia/Taipei）

Case：`0003` / 玉井橋

固定機器：`DESKTOP-UL7V2VV` / `UL7`

固定工作目錄：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`

## 1. 本文件目的

本文件接續 `2026-08-17-1605-Case0003-玉井橋全流程操作手冊與Blender品質回修紀錄.md`。

舊文件中的 `BLENDER REWORK INCOMPLETE` 已被後續 REAL evidence 取代；Blender 已完成可見地形修復。Case 0003 目前真正 owning gap 已轉移到 `liuxb99/SceneX`。

本批新增最後一個人工驗收要求：

> 除了機器驗證、Drive 多模態審查與 Delivery Revision 外，固定工作目錄最後必須留下可雙擊的 BAT，讓人在 UL7 上直接啟動 SceneX 並載入 Case 0003 的真實 Region Pack 看成果。

## 2. 已確認 Blender 新成果

Blender REAL render：

```text
D:\AI-Work\jobs\0003-YUJING-BRIDGE\blender\terrain-render.png
SHA256 = 6d985bd9b1a512ec225d7408a8d3a8eb373cd6494063ee575f834c0fd3b7cada
```

因此後續不得重跑 DTM / AOI / Blender，除非新的 evidence 明確證明這些前置成果發生 provenance drift。

## 3. 舊 Drive Revision 的正確解讀

已發布 revision：

```text
rev_0851c5ab49ff459d83ee1cb6268ea8d3
manifest SHA256 = 349e1c0e2eaad9994cb6989c956cc93c8c38f8bd4a5ff0590eb9870ad788a020
Drive folder id = 1dbQDGsbW1_X3SmX7doPbQ27ElIyCtDJh
current review ZIP file id = 15vrTKyhoObSZXxCFCbRfVDbtGTNnGnPA
```

ChatGPT 實體審查結論：

```text
Blender：地形已可見
SceneX：畫面近乎均一深色，缺乏可辨識地形／橋梁語義
verdict：TOOL_GAP
owning repo：liuxb99/SceneX
```

重要時間線：此 Drive revision 在 SceneX winding 真正修復之前建立，因此不能拿舊 SceneX 圖判定修復後成果失敗。

## 4. SceneX 真正 root cause

### 4.1 Semantic visibility gate

SceneX commit：

```text
5233754d48387b65fad27a315362231c988ca7c6
fix: make REAL terrain browse semantically visible fail closed
```

新增：

- deterministic terrain material
- camera framing 改善
- key/fill lighting
- coarse block luma structure metrics
- `coarse_luma_stddev`
- `coarse_luma_range`

目標：避免「雖然有像素變化，但整張只是平滑暗面」仍被誤判可用。

### 4.2 Godot triangle winding

SceneX commit：

```text
e2b41e5ee202a9f8fe6865ecb75f90066251517d
fix(terrain): use Godot clockwise front-face winding
```

舊 terrain mesh triangle order 會讓上視角看到 back-face，造成 geometry counters > 0，但真正畫面仍看不到地形。

正式修復改用 Godot clockwise front-face winding，並以永久 smoke test 鎖定。

### 4.3 Case 0003 REAL owner workflow

```text
.github/workflows/case-0003-yujing-winding-repair-ul7.yml
```

規則：

```text
UL7 fixed host
→ 使用既有 canonical terrain-grid / terrain-context / geolocation
→ fresh Region Pack
→ winding smoke
→ REAL SceneX browse
→ semantic visibility gate
→ terrain-browse.png + evidence + workspace manifest
```

不得重建 DTM / AOI。

## 5. 新的 SceneX 成果必須滿足

至少必須存在：

```text
scenex\terrain.region.json
scenex\terrain-browse.png
scenex\terrain-browse-evidence.json
scenex\scenex-workspace.json
```

機器 gate：

```text
evidence.ok == true
active_chunk_count > 0
terrain_geometry_count > 0
coarse_luma_stddev >= configured threshold
coarse_luma_range >= configured threshold
```

但這仍只是 mechanical / semantic proxy gate。

下一步仍必須把新的 SceneX PNG 放進 fresh immutable review revision，再由 ChatGPT 實際看圖。

## 6. BAT 最終人工驗收成果

SceneX owning workflow：

```text
.github/workflows/case-0003-yujing-launcher-ul7.yml
```

SceneX commit：

```text
9ffd1232fb0b31267ce8c8a41696b1def9f85017
feat(case0003): materialize SceneX launcher BAT on UL7
```

它在固定工作目錄產生：

```text
D:\AI-Work\jobs\0003-YUJING-BRIDGE\Open-Case0003-SceneX.bat
```

BAT 綁定並驗證：

```text
Godot executable
SceneX real project.godot
Case 0003 scenex\terrain.region.json
```

正常雙擊：

```text
Open-Case0003-SceneX.bat
```

行為：

```text
Godot
→ SceneX 正式 project
→ config/main_scene = region_pack_race_demo.tscn
→ --region-pack=<Case0003 terrain.region.json>
→ 人可以直接進 SceneX 看玉井橋成果
```

CI 驗證模式：

```text
Open-Case0003-SceneX.bat --check-only
```

必須輸出：

```text
CASE0003_SCENEX_LAUNCHER_CHECK_PASS
```

並產生：

```text
scenex\scenex-launcher-evidence.json
```

## 7. 新的完整閉環

```text
DTM / AOI authoritative data
  ↓
Blender REAL + visual gate
  ↓
SceneX REAL + winding + semantic visibility gate
  ↓
fresh immutable review revision
  ↓
Google Drive multimodal review transport
  ↓
ChatGPT exact visual review
  ↓
PASS only
  ↓
WorkLedger review apply
  ↓
Delivery Revision + validation
  ↓
Open-Case0003-SceneX.bat
  ↓
人員在 UL7 實際打開 SceneX 看成果
```

## 8. Fail-closed 規則

以下任何一項不存在，都不得稱 Case 0003 完整 CLOSED：

1. 新 SceneX browse 實圖通過 ChatGPT 多模態審查。
2. fresh review revision 的 manifest / SHA / cloud identity 完整。
3. WorkLedger 已套用 PASS receipt。
4. Delivery Revision validation PASS。
5. `Open-Case0003-SceneX.bat` 存在於固定 workspace。
6. BAT `--check-only` PASS。
7. BAT 啟動的是 SceneX 正式 project + Case0003 Region Pack，不是 PNG viewer、測試替代程式或 fallback demo。

目前下一步：等待／取得 winding 修復後 REAL SceneX browse 實體成果，重新建立 fresh review revision；若視覺仍不合格，只修 SceneX owning presentation/runtime，不回退 DTM/AOI/Blender。
