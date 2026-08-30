# 案例 0003 玉井橋：OpenWorker Final Acceptance / mini-Git 進度

> 更新：2026-08-17 09:35（Asia/Taipei）
>
> 主責 repo：`liuxb99/openworker`
>
> 狀態：`VERIFYING / REAL FINAL ACCEPTANCE QUEUED`
>
> 本文件優先於 2026-08-16 手冊中的 `CLOSED / REAL VERIFIED` 狀態字樣。2026-08-16 的 REAL 全鏈成功證據保留為歷史 baseline，但新版治理要求 OpenWorker 自己重新查驗成果並通過 WorkLedger acceptance gate 後，才可重新標為 `DELIVERED / REAL VERIFIED`。

## 1. 本批目標

把 Case 0003 從「歷史 workflow 成功」升級成：

```text
OpenWorker Job
→ mandatory mini-Git WorkLedger
→ 歷史 REAL evidence 作 baseline provenance
→ UL7 fresh physical/reopen verification
→ required checks
→ ACCEPTED | REWORK_REQUIRED
→ accepted 才能 delivery
```

若任何 required check 失敗，OpenWorker 必須把當前 revision 標成 `REWORK_REQUIRED`，記錄 owning repo、原因與重驗計畫；修復後只能建立 child revision，不得覆寫失敗 revision。

## 2. 本批發現的真缺口

### 2.1 OpenWorker 自己的 Case 0003 workflow 還是舊 8-slot matrix

舊 `.github/workflows/case-0003-yujing-bridge-ul7.yml` 仍為：

```text
runs-on: [self-hosted, Windows, X64]
matrix slot = 1..8
wrong-host → selected=false → skip
```

這和後期已收斂的 UL7 固定路由不一致，也可能產生「一堆 wrong-host skip / queued」噪音。

已修為：

```text
runs-on: [self-hosted, Windows, X64, UL7]
COMPUTERNAME 必須 == DESKTOP-UL7V2VV
錯誤直接 fail closed
```

workflow commit：

`96bde1afddbb6f02f03b275c90a6789f8ba76e8d`

### 2.2 歷史舊 matrix run 仍殘留 queued jobs

舊 run：

- run `31920291957`
- 8 個 `UL7 route (1..8)` jobs 仍為 queued

它們是舊版 workflow 的歷史垃圾，不得再用來判斷 Case 0003 目前狀態，也不應當成產品 job。

GitHub connector 目前沒有 expose cancel-run action，因此本輪不宣稱已清除；新版 workflow 已完全移除 matrix，後續不再產生這類 jobs。

## 3. 新增 OpenWorker REAL Final Acceptance 程式

新增：

`scripts/case0003_final_acceptance.py`

commit：

`2ec3acbc131634f699d914314fd78fd4ab70055f`

它不是讀昨天的 workflow conclusion，而是直接讀 UL7 工作目錄：

`D:\AI-Work\jobs\0003-YUJING-BRIDGE`

並執行下列 required checks。

### DTM

- `D:\TaiwanDTM\catalog\dtm_catalog.sqlite` 必須存在且非零。
- Python SQLite 以 read-only reopen。
- `PRAGMA quick_check` 必須 `ok`。
- 至少存在一個 SQLite table。

owner：`liuxb99/Terrain_To_DXF`

### AOI

重新讀：

- `terrain/terrain-context.json`
- `terrain/terrain-grid.json`

要求：

- bounded workspace path；
- 非空；
- JSON 可解析；
- context schema 必須 `terrain-context/v1`；
- grid 不得為空。

owner：`liuxb99/Terrain_To_DXF`

### Consumer

重新讀：

`consumer/consumer-orchestration.json`

要求非空、可解析、為非空 JSON object。

owner：`liuxb99/Terrain_To_DXF`

### Blender

不是只看 `terrain-scene.blend` 存在。

OpenWorker 會：

1. 驗證 `blender/terrain-scene.blend` 非空；
2. 驗證 `blender/terrain-render.png` 為真正 PNG，讀 IHDR 尺寸；
3. 找到 Blender CLI；
4. 使用 Blender 本體：

```text
blender --background terrain-scene.blend --python blender_reopen_probe.py
```

5. 必須真的 reopen `.blend`；
6. `bpy.data.objects > 0`；
7. `bpy.data.scenes > 0`；
8. 寫出新的：

`acceptance/openworker-final/blender-reopen-evidence.json`

owner：`liuxb99/Terrain_To_DXF`

### SceneX

SceneX 不接受昨天 screenshot 作為 fresh acceptance。

新版 workflow 會 checkout `liuxb99/SceneX@master`，再用 canonical Terrain outputs：

- `terrain/terrain-grid.json`
- `terrain/terrain-context.json`
- `geo/geolocation.json`

重新 build：

`scenex/terrain.region.json`

再使用 SceneX production `workspace_region_pack_browse.gd` + Godot 4.6.3 / Forward+ / D3D12 真實執行，重新產生：

- `scenex/terrain-browse.png`
- `scenex/terrain-browse-evidence.json`
- `scenex/scenex-workspace.json`

required gate：

- `scenex-real-browse/v1`
- `ok = true`
- 禁止 `fallback-generated`
- active terrain chunk > 0
- terrain geometry > 0
- evidence viewport = 1280×720
- PNG IHDR = 1280×720

owner：`liuxb99/SceneX`

### OS / Delivery

重新讀 canonical website：

`os/jobs/OWJ-20260816030152-03D90D_0003-YUJING-BRIDGE_OpenWorker_run_job_9d9ee94e021ed007f3aa13c67a40acc5/delivery/website/index.html`

要求：

- bounded workspace path；
- 非空；
- 真正可辨識 HTML；
- delivery tree 至少存在一個非空檔案。

owner：`liuxb99/AI-Engineering-OS`

## 4. WorkLedger 行為

Final Acceptance 會使用 Case 0003 authoritative binding：

- Project Code：`OW-2786FE219ABF`
- Project ID：`prj_ba726e251d380d72507e2172d4946d78`
- Job Code：`OWJ-20260816030152-03D90D`
- Job ID：`job_9d9ee94e021ed007f3aa13c67a40acc5`
- host：`DESKTOP-UL7V2VV`

每個重新讀到的 physical artifact 都會計算 SHA256 並掛到當前 revision。

required checks：

```text
DTM
AOI
Consumer
Blender
SceneX
OS
Delivery
```

只要其中一個 FAIL：

```text
current revision
→ required check = failed
→ REWORK_REQUIRED
→ gap_owner_repo = owning repo
→ verification_plan = repair → REAL rerun → Final Acceptance rerun
```

全部 PASS 才可：

```text
accept_revision()
→ accepted_revision_id = current revision
→ deliver_revision()
→ delivered_revision_id = accepted_revision_id
```

最後會寫：

`acceptance/openworker-final/work-ledger-final-acceptance.json`

## 5. 本批 workflow

正式 REAL Final Acceptance run：

- run：`31985238498`
- job：`95258999260`
- workflow：`Case 0003 Yujing Bridge OpenWorker Final Acceptance UL7`
- head：`96bde1afddbb6f02f03b275c90a6789f8ba76e8d`
- 本次更新時狀態：`queued`

此 run 尚未開始 business execution，因此本文件**不得**把 Case 0003 宣告為新版 Final Acceptance PASS。

主 CI 同一 head：

- run：`31985238481`
- 本次更新時：`in_progress`

## 6. 狀態判定

2026-08-16 的以下 REAL 成功證據仍保留：

- DTM：`31930815026 / 95129023092`
- AOI：`31937722103 / 95142177183`
- Consumer：`31937749499 / 95142253514`
- Blender：`31937773773 / 95142315440`
- SceneX：`31937803580 / 95142388557`
- OS full driver：`31937694129 / 95142102663`
- Delivery ID：`del_94628aca0f2a79003136e16c78141a7f`

但目前正式治理狀態應為：

`VERIFYING / OPENWORKER FINAL ACCEPTANCE QUEUED`

而不是只因舊 manual 有 `CLOSED / REAL VERIFIED` 就直接算完成。

## 7. 下一個 acceptance 分支

如果 run `31985238498` 全 PASS：

- 保存新的 SceneX fresh screenshot/evidence；
- 保存 Blender reopen evidence；
- 保存 WorkLedger snapshot；
- 記錄 accepted/delivered revision；
- 再把案例狀態更新成 `DELIVERED / OPENWORKER REAL VERIFIED`。

如果任何步驟 FAIL：

- 不做人工 workaround；
- 讀 `work-ledger-final-acceptance.json` 的 failed check / `gap_owner_repo`；
- 修真正 owning repo；
- 在 WorkLedger 建立 child rework revision；
- 只重跑必要 REAL product stage；
- 再跑本 Final Acceptance。
