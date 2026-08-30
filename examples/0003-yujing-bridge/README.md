# 案例 0003：臺南市玉井橋 REAL local-first 操作手冊

> Canonical owner：OpenWorker `examples/0003-yujing-bridge/`  
> 固定主機：`DESKTOP-UL7V2VV`（UL7）  
> Canonical workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`  
> Canonical input：`location_text = 臺南市玉井橋`  
> Canonical execution：**OpenWorker local controller → go-tool localexec → owning repo local runtime**  
> GitHub Actions：CI / fallback / bootstrap / 歷史 evidence transport；**不是日常 business execution plane**。

## 0. 本文件是正式操作手冊

本案例不是一次性 smoke test。每一次 REAL 執行都必須把做法、physical artifacts、SHA256、QC、缺口、修復 commit、重跑結果與下一步回寫 `STATUS.md` / `evidence/`。舊流程若被取代，保留為 historical provenance，但不得繼續當 canonical 指令。

目前 canonical 路徑：

```text
ChatGPT / local supervisor
→ OpenWorker 本機總控
→ durable jobs / agent slots / fixed UL7 / workspace authority
→ go-tool localexec capability
→ Terrain / SceneX / AI-Engineering-OS owning runtime
→ physical artifact + semantic/geometry/SHA QC
→ OS Artifact Registry / Review / Delivery
→ immutable Google Drive review ZIP
→ ChatGPT connector visual/semantic review
→ WorkLedger accept / deliver
```

### 執行鐵律

1. OpenWorker 是 fixed-host、workspace、durable queue、agent slot、JobBinding 與 case orchestration authority。
2. go-tool-runtime 是 capability discovery + `localexec` execution registry；模型不得依舊 workflow metadata自行選 GitHub-first。
3. owning repo 才能改真正 producer / 3D / OS delivery 行為；案例腳本不得用假 artifact 遮缺口。
4. `submitted`、job green、Action success 都不是 acceptance。REAL acceptance 一律看 physical bytes + identity + semantic/geometry + SHA256。
5. queue 真阻塞時使用 OpenWorker one-call drain；不得無條件清掉同機其他案例工作。
6. 每個 stage 的 accepted evidence 必須綁 current accepted GEO / host / workspace；GEO 或 bytes 改變，舊 evidence 自動失效。
7. Whole Case `accepted_revision_id / delivered_revision_id` 只能由最終 Drive/ChatGPT PASS 閉環移動；中間 stage 只能寫 progress history。

## 1. Canonical 一鍵入口

在 UL7 使用最新版 OpenWorker：

```powershell
.\scripts\case0003_local_continue_auto.ps1
```

auto entrypoint 做：

```text
persisted machine roots / node inventory
→ JobBinding project/job identity
→ REAL preflight
→ local physical-gate controller
→ strict imagery stage history（僅在真 PASS 後）
```

OpenWorker machine roots 預設持久化於：

`%ProgramData%\OpenWorker\machine-roots.json`

必要時用：

`openworker/scripts/openworker_set_machine_roots.ps1`

目前 authority roots：`OPENWORKER_ROOT / GO_TOOL_ROOT / TERRAIN_ROOT / SCENEX_ROOT / ENGINEERING_OS_ROOT / OPENWORKER_REVIEW_DRIVE_ROOT`。

## 2. Preflight

`case0003_local_preflight.ps1` 在提交 business job 前必須通過：

- host = `DESKTOP-UL7V2VV`；
- OpenWorker node identity 正確；
- go / python / powershell 與各 authority root available；
- canonical workspace 存在；
- `.openworker\job-binding.json` 的 host/workspace/project/job identity 一致；
- `D:\TaiwanDTM\catalog\dtm_catalog.sqlite` 存在且非空；
- AI-Engineering-OS `/healthz` 可用。

Preflight fail 時不得先提交 imagery / AOI / SceneX / Blender jobs。

## 3. GEO — 已 ACCEPTED

Canonical：

`D:\AI-Work\jobs\0003-YUJING-BRIDGE\geo\geolocation.json`

Terrain、Street View、Orthophoto、AOI、SceneX 都必須讀這份 accepted GEO，不得硬寫座標。

## 4. Imagery — producer/contract 已補，REAL UL7 acceptance 待執行

OpenWorker submit：`scripts/case0003_local_imagery_parallel.ps1`  
go-tool capabilities：

- `terrain.streetview.acquire`
- `terrain.orthophoto.acquire`

兩個 stage 使用不同 lock / agent slot，可並行；單邊已 strict PASS 時只重跑另一邊。

### 4.1 Street View strict contract

Canonical manifest：

`streetview\browser\streetview-browser-screenshots.json`

目前 schema：`streetview-browser-screenshots/v3`。

必須同時滿足：

- `transport=localexec`；assigned host = UL7；
- manifest geolocation = current accepted GEO；
- heading 恰為 0 / 90 / 180 / 270，無重複；
- producer = `google / headless-render-webgl / angle-swiftshader-webgl`；
- 1920×1080、bytes > 0；
- producer 已 decode PNG 並做 semantic visibility；黑圖／近黑／近均勻圖 fail；
- 每張 physical PNG SHA256 = producer receipt SHA256；
- output path = manifest path；path 必須位於 canonical workspace。

歷史黑圖全部視為 invalid evidence。

### 4.2 Orthophoto strict contract

Canonical workspace manifest：

`orthophoto\nlsc-photo2\orthophoto-photo2-workspace.json`

目前 schema：`orthophoto-workspace/v2`。

必須同時滿足：

- `transport=localexec`；assigned host = UL7；
- manifest geolocation = current accepted GEO；
- producer schema `orthophoto-nlsc-photo2/v1`；
- provider=`nlsc`、layer=`PHOTO2`、zoom=19、tile count 1..25；
- producer plan lat/lng = current accepted GEO；
- `visibility.visible=true`；
- useful pixel ratio >= 0.20；luma stddev >= 0.02；luma range >= 0.10；
- physical JPEG SHA256 = producer `output_sha256`；dimensions/bytes > 0；
- JPG / evidence / manifest 必須位於 canonical workspace。

舊只有 `orthophoto-photo2-evidence.json` 的成果不能 PASS。

### 4.3 Imagery stage WorkLedger history

只有 Street View + Orthophoto strict gate 同時通過，auto entrypoint 才執行：

`scripts/case0003_record_imagery_acceptance.py`

它建立／復用 WorkLedger `progress` revision，記錄 current GEO、四張街景、PHOTO2 JPG、workspace manifests 與 physical SHA，並把三個 imagery required checks 設為 passed；revision 保持 `verifying`。

**它不得呼叫 whole-case `accept_revision()` 或 `deliver_revision()`。** 同一 fingerprint 重跑 idempotent；GEO 或任何 imagery bytes 改變即形成不同 fingerprint。

## 5. Terrain AOI

Terrain owning entrypoint：`Terrain_To_DXF/scripts/terrain_aoi_local.ps1`  
go-tool：`terrain.aoi.build`  
OpenWorker：`scripts/case0003_local_terrain_aoi.ps1`

REAL gate：10 個 non-empty artifacts（context/build/grid/DXF/heightmap raw+json/OBJ/mesh/scene/SceneX handoff）、`terrain-context/v1`、`usable_tiles > 0`、physical SHA evidence。

## 6. Terrain downstream + SceneX

Terrain gate 後可並行：

```text
Terrain
├→ SceneX REAL browse
└→ strict imagery pass → Consumer → Blender REAL
```

Consumer：`terrain.consumer.orchestrate` / `scripts/case0003_local_consumer.ps1`。  
Blender：`terrain.blender.execute` / `scripts/case0003_local_blender.ps1`。  
SceneX：`scenex.terrain.real_browse` / `scripts/case0003_local_scenex.ps1`。

Blender 必須有真 `.blend`、render、request/evidence/handoff 與 scene/render SHA 一致。SceneX 必須 active chunks > 0、terrain geometry > 0、1280×720 screenshot、region/evidence/screenshot SHA 一致。

## 7. AI-Engineering-OS

Blender + SceneX pass 後：

1. `engineering_os.artifacts.ingest`：ArtifactStager 將外部 workspace artifact 安全 stage 入 OS Job WorkingDir，再 recompute SHA，不放寬 JobPathValidator。
2. current artifacts 必須經 OS Review / Approval。
3. `engineering_os.delivery.publish` 只在 approval-status 通過後 publish。
4. publish 後重新驗 delivery manifest、checksum manifest、website 與 revision identity。

OS project/job identity來自 persisted JobBinding；explicit override 不一致時 fail-closed。

## 8. Google Drive / ChatGPT review

Google Drive 只作 review exchange，不作 business execution transport。

OS Delivery 通過後：

- `case0003_prepare_drive_review.py` 做 fresh mechanical verification；
- `case0003_seal_drive_review.py` 產生 deterministic immutable `<revision_id>.zip`；
- Drive sync folder 與 local ZIP SHA 必須一致；
- ChatGPT connector 必須實際查看 Blender render、SceneX screenshot、evidence、delivery website；
- verdict = PASS / TUNE / FAIL / TOOL_GAP；
- canonical return inbox = `connector-review-receipt.json`；
- receipt 必須綁 revision ID、bundle manifest SHA、review ZIP SHA、Drive folder/file IDs。

PASS 只先進 `ACCEPTED_PENDING_FINALIZE`。Reviewed delivery finalizer 再綁 current OS delivery identity、current physical bytes、Drive identity、WorkLedger accepted pointer；全部一致才可 `DELIVERED`。

## 9. Acceptance boundary

目前只有 GEO 可稱 whole-stage歷史上已 ACCEPTED。Street View / Orthophoto 的 code、localexec、semantic visibility、SHA、GEO binding、stage-history contract 已補齊，但 **尚未取得最新版 UL7 REAL v3/v2 imagery，因此目前仍不能聲稱 imagery REAL ACCEPTED。**

Whole Case 尚不得稱 ACCEPTED/DELIVERED，直到：

```text
fresh imagery
→ AOI
→ Consumer/Blender + SceneX
→ OS Registry/Review/Delivery
→ Drive immutable review
→ ChatGPT connector PASS
→ finalizer
→ WorkLedger delivered
```

## 10. 歷史 GitHub-first provenance

2026-08-16 前後曾使用 self-hosted GitHub Actions / runner IDs 驗證 UL7 online、bootstrap 與舊流程。這些 run ID 只作歷史 provenance。若舊文檔提到 `workflow_dispatch → self-hosted runner → business artifact`，一律視為 **deprecated / replaced by OpenWorker local-first**，不得作為新的 Case 0003 執行指令。
