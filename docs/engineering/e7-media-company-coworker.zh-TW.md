# E7 Media / Company Coworker 開發進度

更新日期：2026-08-14

## 目標與固定邊界

E7 讓 OpenWorker 的 Media / Company Coworker 把工作轉成可保存、可交接、可執行、可驗證、可交付的產品流程，但不再造第二套平台。

固定邊界：

- 不新增第二套 Agent loop / Tool Registry / Scheduler / Connector layer / Artifact Registry。
- NativeRuntime 預設；Harness 只允許 explicit opt-in。
- canonical engineering / media Job authority 固定由 AI-Engineering-OS control plane 管理；ComfyX 等 specialist engine 只擁有自己的專業執行契約。
- send / publish / spend / purchase / commitment 必須保留既有 approval gate。
- Persona 模組只做產品 contract、lineage、handoff、evidence sync 與 result projection，不直接偷跑外部副作用。

## E7.1～E7.4

狀態：`IMPLEMENTED / MAIN CI VERIFIED；WIN11 FOCUSED GATE PENDING`

已完成 Media/Company built-in personas、declarative Task Package、Persona Product Contract、canonical AI-Engineering-OS Job submission/reuse 與 delivery assessment。E7.4 main CI `31790725031` 全綠。

## E7.5 — Canonical Execution / Result Bridge

狀態：`IMPLEMENTED / MAIN CI VERIFIED；WIN11 FOCUSED GATE PENDING`

Persona 只建立既有 Tool Registry 可執行的 `CanonicalToolCall` descriptor；RC-column 委派 AI-Engineering-OS authoritative flow。`read_canonical_result()` 只回讀 canonical Job/Artifact/Review/approval，任何 lineage 衝突 fail closed，且永遠不宣稱已 publish/send。

## E7.6 — Authoritative Media Canonical Submit Facade

狀態：`IMPLEMENTED / MAIN CI VERIFIED；WIN11 FOCUSED GATE PENDING`

權威入口固定為：

```text
protocol_version = ai-tool-protocol/1.0.0
tool_id          = comfyx.minimax_h3.generate
```

OpenWorker 的 `ComfyXToolClient` 只做 protocol adapter；Desktop runtime discovery、MiniMax H3 五模式 prompt build、ComfyUI submission/poll、history 與 output extraction 都由 ComfyX 負責。Media persona 經既有 `engineering_os` catalog capability 使用 `engineering_generate_minimax_h3`，沒有新增第二套 registry/scheduler。

Main CI `31793729770` 已 completed / success，`pytest + gui-unit/typecheck + gui-e2e` 全綠。

## E7.7 — ComfyX Result → Canonical Artifact/Evidence Sync

狀態：`IMPLEMENTED — MAIN CI RE-VERIFYING WITH E7.8；WIN11 FOCUSED GATE PENDING`

核心：`coworker/personas/media_evidence.py`、`tests/test_e7_media_evidence.py`。

`sync_comfyx_media_evidence()` 會先核對 AI-Engineering-OS canonical Job 的 project/persona/session/task-package lineage，然後才接受 ComfyX durable artifact。

MP4 evidence 路線：

```text
explicit local uri/path
→ file exists
→ inspect_mp4() ISO-BMFF validation
→ SHA-256 streaming checksum
→ EngineeringOSClient.register_artifact(...)
→ os_artifact_ref()
```

Canonical registration 固定：

```text
project_id = PersonaJobSubmission.project_id
job_id = PersonaJobSubmission.job_id
kind = animation_video
media_type = video/mp4
checksum = actual local SHA-256
source_run_id = ComfyX prompt_id
```

E7.8 後，E7.7 也會交叉驗證 ComfyX 宣告的 `size` 與 `sha256`；若 ComfyX metadata 與實際 materialized bytes 不一致，會在 Artifact Registry mutation 前 fail closed。

## E7.8 — ComfyX Durable Artifact Location Contract

狀態：`IMPLEMENTED — COMFYX CI / OPENWORKER CI IN PROGRESS`

這批直接修改 domain authority `liuxb99/ComfyX`，沒有把 output-path 猜測搬進 Persona/OpenWorker。

### 1. 不再猜 ComfyUI output directory

原本 ComfyX `artifact.Extract()` 只提供：

```text
node_id
kind
filename
subfolder
type
url = /view?filename=...&subfolder=...&type=...
```

這些值足以讓 ComfyUI 取回輸出，但不足以作為 AI-Engineering-OS durable Artifact evidence。

E7.8 沒有使用：

```text
<Desktop install>/output
COMFYUI/output
固定 D:\... 路徑
```

因為這些做法在 Desktop、自訂 output_dir、不同機器與 external runtime 都不可靠。

### 2. 新增 ComfyX-owned materialization

新增：

```text
internal/comfyui/artifact/materialize.go
Materialize(ctx, baseURL, promptID, root, artifacts)
```

ComfyX 直接使用 authoritative artifact `/view?...` URL 把真實 bytes 複製到自己的 artifact cache：

```text
COMFYX_ARTIFACT_DIR
或 <OS user cache>/ComfyX/artifacts
或 temp fallback
```

結構：

```text
<artifact-root>/<prompt_id>/<node_id>/<kind>/<filename>
```

因此 durable location 是 **ComfyX 實際寫出的本地副本**，不是從 ComfyUI 安裝路徑反推。

### 3. DurableArtifact contract

H3 artifact 現在保留原始 ComfyUI identity，同時新增：

```text
uri
size
sha256
media_type
```

完整概念：

```text
node_id / kind / filename / subfolder / type / url
+ uri / size / sha256 / media_type
```

Materialize 使用 streaming copy + streaming SHA-256；空輸出直接失敗。寫檔先進 `.tmp`，成功後 rename，避免把半寫 artifact 暴露成 durable evidence。Filename 使用 basename，禁止藉由 ComfyUI filename 逃出 ComfyX artifact root。

### 4. `comfyx.minimax_h3.generate` 已接入 durable materialization

`cmd/comfyx-tool/main.go` 現在流程：

```text
runner.Run()
→ prompt_id + history
→ artifact.Extract()
→ artifact.Materialize(selected.BaseURL, prompt_id, ...)
→ durable artifacts
→ ai-tool-protocol response
```

若 `/view` 下載、materialization、空檔或 rename 任一步失敗，H3 tool 整體 fail closed，不會回報一份無法驗證的成功 artifact。

Tool version 已提升至 `1.4.0`。

### 5. ComfyX regression

新增：

```text
internal/comfyui/artifact/materialize_test.go
```

鎖定：

- `/view` 真實 bytes 必須寫入 durable URI。
- size 必須等於實際 bytes。
- sha256 必須等於實際 bytes。
- media type 要保留/推導。
- 空輸出拒絕。
- artifact filename 的 `../` 不得造成 path traversal。

另外新增 `.github/workflows/artifact-contract-ci.yml`：

```text
go test ./internal/comfyui/artifact -count=1 -v
go test ./cmd/comfyx-tool -count=1
```

用來快速驗證 artifact contract 與 authoritative tool facade 的 compile contract；原有 G12/G15 self-hosted Windows H3 workflow 仍負責真實 GPU/Desktop 驗證。

### 6. OpenWorker 已開始消費新 contract

`coworker/personas/media_evidence.py` 現在除了重新計算本地 SHA-256，也會交叉檢查：

```text
ComfyX size == local stat().st_size
ComfyX sha256 == OpenWorker recomputed SHA-256
```

任一不一致都不呼叫 `register_artifact()`。

所以跨 repo evidence chain 現在是：

```text
ComfyUI actual output
→ ComfyX /view
→ ComfyX durable materialized copy
→ uri + size + sha256 + media_type
→ OpenWorker format/size/checksum re-validation
→ AI-Engineering-OS register_artifact
→ canonical EvidenceRef
```

這已消除 E7.7 原本最大的「真實 H3 output 沒有 authoritative local URI」缺口。

## CI / Win11 驗證狀態

```text
E7.1～E7.4 main CI: VERIFIED
E7.6 main CI:       31793729770 → ALL SUCCESS
E7.8 OpenWorker CI: 31794621931 → IN PROGRESS
E7 focused Win11:   31794621999 → QUEUED
ComfyX artifact CI: 31794670101 → QUEUED / STARTING
ComfyX G12 H3:      31794558886 → QUEUED (self-hosted Windows)
ComfyX G15 H3:      latest E7.8-triggered run queued (self-hosted Windows)
```

Self-hosted Windows queued 只代表 runner 尚未接單，不視為代碼失敗。

## 下一批 E7.9 — Real Media End-to-End Closure

E7.8 已把 specialist output → durable local evidence 的 contract 補齊。下一批不應再增加抽象層，而是直接用真實 H3 跑一次完整產品閉環：

```text
Media PersonaTaskPackage
→ PersonaProductPlan
→ AI-Engineering-OS canonical Job
→ media_submit_tool_call()
→ engineering_generate_minimax_h3
→ comfyx.minimax_h3.generate
→ durable ComfyX artifact
→ sync_comfyx_media_evidence()
→ AI-Engineering-OS Artifact Registry
→ read_canonical_result()
→ QA / review / approval
→ assess_delivery_readiness()
```

驗收重點：

- 真實非空 MP4。
- ComfyX sha256 與 OpenWorker 重算一致。
- Artifact Registry checksum 一致。
- `source_run_id == prompt_id`。
- Job/persona/session/task-package lineage 不斷鏈。
- 未經 approval 絕不 publish/send。
- 真實生成與 evidence sync 成功後才把 E7 Media 主線標成 end-to-end closed。
