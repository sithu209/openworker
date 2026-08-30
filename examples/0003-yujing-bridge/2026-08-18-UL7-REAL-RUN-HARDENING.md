# Case 0003 玉井橋 — UL7 REAL 首跑前硬化

日期：2026-08-18

## 目的

本批不新增案例功能，而是針對 `DESKTOP-UL7V2VV` 第一次以新版 local-first controller REAL 跑穿前，檢查會造成錯誤選路、重複 revision、stale review 或 false delivery 的缺口。

## 1. go-tool discovery authority 對齊 execution reality

發現：Terrain localexec 已存在，但 `config.yaml` 的 Street View / AOI / Consumer / Blender metadata 仍保留 GitHub workflow-first 描述。

修正於 `liuxb99/go-tool-runtime`：

- `93c2cfe7e692034e84e55fc63f90b25155e725a9`
- `56b0f2c31e1d074069054692c27f7a0e666b1ad9`
- test `addc6a7045f9de682d3eff9020517aebd1213ee3`

四個 capability 在 config Load 後 canonicalize 為 `execution.mode=local_action`：

```text
terrain.streetview.acquire
terrain.aoi.build
terrain.consumer.orchestrate
terrain.blender.execute
```

舊 workflow / runner metadata 僅保留 fallback / CI provenance。

Execution reality 已重新核對：

- Street View / Orthophoto / AOI：`internal/localexec/terrain_local.go`
- Consumer / Blender：`internal/localexec/terrain_downstream_local.go`
- `cmd/gtr-local-exec/main.go` 明確執行 `RegisterTerrainDownstream(terrainRoot)`。

## 2. OpenWorker one-call queue drain reality check

新版 Go runtime 已有：

```text
POST /v1/queue/drain?mode=queued
POST /v1/queue/drain?mode=all
POST /v1/cluster/queue/drain
```

Case controller 不無條件自動 drain，因為 local queue 可能同時含其他 Case；真正判定 blockage 時由 supervisor/model 一次呼叫官方 drain，而不是逐筆清 job。

Controller duplicate suppression 使用的狀態也已與 Go runtime 核對一致：

```text
accepted
queued_local
starting
running
```

## 3. Drive review prepare retry 不再產生多餘 revision

發現：舊 v2 durable submit 是：

```text
prepare new review revision
→ seal ZIP
```

若 prepare 已成功、seal/sync 暫時失敗，下一次重跑會再開一個新的 review revision，留下多個 WAITING_DRIVE_REVIEW revision/folder。

修正：

- `8c2882ea4905f3bf01e5aa19dbc2d49016f70c89`
- test `fe8508a8be0fa43e0920b76366329513f249e4ea`

現在若 existing prepare v1/v2 receipt 還是 `WAITING_DRIVE_REVIEW`，且 bundle / Drive target 仍存在，就進：

```text
mode=resume_seal
→ 只執行 case0003_seal_drive_review.py
→ 不再 open new WorkLedger revision
```

否則才執行 `prepare_and_seal`。

## 4. ChatGPT PASS 必須綁定被審查的 OS Delivery bytes

發現一個高風險 stale-delivery 缺口：Review PASS 已綁 bundle SHA / Drive ZIP SHA，但 finalizer 原先只驗「當下 OS delivery receipt 與當下檔案彼此一致」，沒有再確認當下 OS delivery bytes 等於 ChatGPT 當時看過的 delivery artifacts。

若 review 完後 OS 又發布新 revision，舊 PASS 不應有資格 finalize 新 bytes。

修正：

- finalizer hardening：`e6276a940c16df4b4e6c645d4b2c045df20f6a02`
- compatibility alias：`b5f0c9d8bb7ee3d8ba23768f3e473b3b9a1b6192`
- local submit：`a0f59e6131f5a54977c08f1fb301eadcb5263ec0`
- regression tests：`ac84761afcb05954535cb1e0147232754c5b03cd`

Finalizer 現在從 reviewed bundle manifest 取出並固定：

```text
delivery-manifest SHA256
checksum-manifest SHA256
delivery-index website SHA256
```

然後再計算目前 Engineering OS delivery 的三個 physical SHA。任何一項不同：

```text
FAIL CLOSED
→ 不移動 delivered_revision_id
```

per-revision finalizer evidence 使用 v3；controller 目前仍讀 v2 latest schema，因此 canonical wrapper 只在 v3 receipt 已驗證 `DELIVERED` 且 reviewed byte binding 完整後，產生帶 `semantic_contract_version=v3` 的 v2 compatibility latest alias。這不降低 v3 驗證，只維持 controller compatibility。

## 5. Acceptance boundary

本批是 execution / retry / evidence-integrity hardening。

**不得因此新增任何 ACCEPTED stage。**

目前仍只有：

```text
GEO = ACCEPTED
```

Street View、Orthophoto、Terrain AOI、Consumer、Blender、SceneX、OS Artifact Registry/Approval/Delivery、Drive ChatGPT review 都仍需 UL7 fresh REAL physical execution/QC。

下一個真正有價值的動作仍是以最新版 OpenWorker + go-tool 在 UL7 跑 `scripts/case0003_local_continue.ps1`，讓真實執行暴露剩餘缺口。
