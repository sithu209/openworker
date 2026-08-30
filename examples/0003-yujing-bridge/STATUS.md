# 0003 臺南市玉井橋 — STATUS

更新時間：2026-08-18 Asia/Taipei

狀態：`IMPLEMENTING / GEO ACCEPTED / IMAGERY+TERRAIN+CONSUMER+RENDER STRICT CHAIN IMPLEMENTED / OS SOURCE-BINDING IMPLEMENTED / DRIVE REVIEW LOOP LOCALIZED / UL7 REAL REQUIRED`

## 1. Canonical authority

- Host：`DESKTOP-UL7V2VV`
- Workspace：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- Input：`臺南市玉井橋`
- OpenWorker：本機總控、durable queue、agent slots、host/workspace/JobBinding authority。
- go-tool-runtime：capability discovery + `localexec`。
- owning repos：真正 imagery / terrain / Blender / SceneX / OS logic authority。
- GitHub Actions：CI / fallback / bootstrap / historical evidence；不是 canonical business execution plane。

Canonical current-chain：

```text
GEO
→ Imagery fingerprint
→ Terrain fingerprint
→ Consumer fingerprint
→ Blender + SceneX render fingerprint
→ OS artifact-ingest/v2 source_binding
→ OS Review / Approval
→ OS Delivery
→ immutable Drive review ZIP
→ ChatGPT connector review
→ WorkLedger final accept / deliver
```

## 2. Acceptance boundary

目前 whole-case 只有 GEO 可稱 ACCEPTED。Street View、Orthophoto、Terrain、Consumer、Blender、SceneX、OS Registry、OS Delivery 皆仍需 UL7 fresh REAL execution / physical QC。

程式 contract 已經 fail-closed，但 IMPLEMENTED 不等於 REAL VERIFIED。

## 3. Canonical auto entrypoint

`scripts/case0003_local_continue_auto.ps1`

目前 root-resolution schema：`openworker/case0003-root-resolution/v11`。

controller 前順序：

```text
machine-root / JobBinding / REAL preflight
→ imagery unsafe/stale quarantine
→ terrain stale quarantine
→ consumer stale quarantine
→ Blender/SceneX stale quarantine
→ OS artifact source-binding guard
→ v10 physical-gate controller
→ stage WorkLedger recorders
```

任何 quarantine 都保留舊 evidence，不直接刪除。

## 4. Imagery strict contract

Street View：`streetview-browser-screenshots/v3`；綁 current GEO、UL7/localexec、4 headings、Google headless renderer provenance、semantic visibility、1920×1080、physical SHA、workspace containment。

Orthophoto：`orthophoto-workspace/v2`；綁 current GEO / producer plan GEO、NLSC PHOTO2 z19 bounded tiles、semantic visibility、physical JPEG SHA、workspace containment。

兩邊 strict PASS 後，`case0003_record_imagery_acceptance.py` 建立 WorkLedger `progress/verifying` history；不得移動 whole-case accepted/delivered pointer。

## 5. Terrain strict contract

Terrain producer：`terrain-aoi-workspace/v2`。

綁：
- current GEO lat/lng + GEO SHA；
- DTM catalog path/size/SHA；
- AOI build request SHA；
- 10 個 terrain artifacts path/size/SHA；
- host/workspace identity、usable DTM tiles。

`case0003_quarantine_stale_terrain.ps1` 在 GEO/catalog/request/artifact 任一漂移時隔離舊 `terrain\`。

`case0003_record_terrain_acceptance.py` 只寫 stage `progress/verifying` history。

## 6. Consumer strict contract

Producer：`consumer-workspace/v2`。

綁：
- current GEO SHA；
- imagery acceptance fingerprint；
- terrain acceptance fingerprint + terrain workspace SHA；
- terrain mesh SHA；
- 7 個 consumer output SHA。

`case0003_quarantine_stale_consumer.ps1` 在 upstream fingerprint 或 physical SHA 漂移時隔離舊 `consumer\`。

## 7. Blender + SceneX strict render chain

Blender：`blender-workspace/v2`，綁 current `consumer_fingerprint`、consumer workspace/orchestration SHA，以及 `.blend/render/request/evidence/handoff` physical SHA，產生 `blender_fingerprint`。

SceneX：`scenex-workspace-browse/v2`，綁 current `terrain_fingerprint`、terrain manifest SHA、GEO SHA，以及 Region Pack / screenshot / evidence SHA，產生 `scenex_fingerprint`。

`case0003_quarantine_stale_render_outputs.ps1` 會隔離任何 stale Blender/SceneX outputs。

`case0003_record_render_acceptance.py` 只有兩邊 current-chain一致時才建立 `acceptance\render\render-acceptance.json` 與 WorkLedger `progress/verifying` history。

## 8. AI-Engineering-OS source binding

Case 0003 OS ingest現在使用：

`artifact-ingest/v2`

新增 `source_binding`：

```text
render_fingerprint
blender_fingerprint
scenex_fingerprint
```

AI-Engineering-OS command保留 v1 read compatibility，但 v2必須有 non-empty source binding；v2 receipt為 `engineering-os-artifact-ingest-receipt/v2` 並原樣回傳 binding。

go-tool localexec也會驗 v2 receipt沒有丟失 source binding。

OpenWorker `case0003_guard_os_artifact_binding.ps1` 在 controller 前：
- 比對 OS receipt source binding與 current render acceptance；
- stale時把 OS ingest evidence移入 `.openworker\quarantine\os-artifacts\`；
- current v2 receipt保留 raw v2檔，另產 controller-compatible latest view，帶 `semantic_contract_version=v2`。

OS Delivery submit v2除了 approval=true，還必須證明 current OS ingest compatibility view確實由 v2 source binding支撐，且三個 fingerprints仍等於 current render acceptance；否則不發布。

## 9. Drive / ChatGPT final review

OS Delivery pass後：fresh mechanical verification → immutable deterministic ZIP → Drive sync。

ChatGPT connector 必須實際查看 Blender render、SceneX screenshot、evidence、delivery website，回傳 PASS/TUNE/FAIL/TOOL_GAP receipt，綁 current revision、bundle manifest SHA、ZIP SHA與 Drive folder/file identity。

PASS 只先進 `ACCEPTED_PENDING_FINALIZE`；finalizer再驗 current OS delivery bytes仍等於 reviewed bytes，全部一致才移動 WorkLedger delivered pointer。

## 10. Next REAL action

UL7 使用最新版 OpenWorker / go-tool / Terrain / SceneX / AI-Engineering-OS：

```powershell
.\scripts\case0003_local_continue_auto.ps1
```

預期 stale imagery / terrain / consumer / render / OS registry evidence會依 current-chain contract被隔離，fresh local durable jobs重新建立成果。

此 ChatGPT 執行環境目前沒有直接到 UL7 `127.0.0.1:8787` 的執行通道，所以本輪不能假稱已提交 UL7 job或已產生 fresh REAL artifacts。
