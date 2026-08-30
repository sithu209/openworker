# OpenWorker × DeepSeek Harness H7-H11 開發進度

更新日期：2026-08-14

本文件是 H7-H11 的最新狀態摘要。狀態分為：

- `IMPLEMENTED`：代碼與永久測試已完成。
- `VERIFIED`：已取得指定的真實 Win11 / official Harness / hardware 證據。
- `REAL-HARDWARE-PENDING`：驗證器與程式已完成，但仍缺真實專業引擎/GPU成果，不提前宣稱成功。

## H7 Runtime jobs / interrupt / cancellation

狀態：`IMPLEMENTED — WIN11 H3-H11 GATE QUEUED`

新增：

```text
coworker/runtimes/harness_jobs.py
coworker/runtimes/harness_managed.py
tests/runtimes/test_harness_jobs.py
tests/runtimes/test_harness_managed.py
```

正式身份分層：

```text
Harness runtime job id = process-local runtime control
ACP session id          = connection-local Harness session
Engineering-OS job id   = durable engineering Digital Thread authority
```

取消順序固定：

```text
OpenWorker request_interrupt
→ Harness runtime job: running → stopping
→ ACP session/cancel
→ Harness turn 真正回 interrupted
→ GET Engineering-OS Job 最新 revision
→ POST /api/v1/jobs/{id}/transitions target=cancelled
→ runtime job: killed
```

若 OS cancel 失敗，runtime job 轉 `failed`，不得把 UI 偽裝成已取消。completed/published/archived Job 不會被覆寫成 cancelled。

## H8 RC Golden Job Native vs Harness A/B

狀態：`IMPLEMENTED — REAL-RC-A/B-PENDING`

新增：

```text
coworker/engineering/runtime_ab.py
tests/test_engineering_runtime_ab.py
```

A/B 不比較 runtime 私有 transcript，也不把兩次同一 helper 呼叫偽裝成 runtime 比較；兩邊都必須走 `AgentRuntime.run()`，並從 AI-Engineering-OS 重新讀取 authoritative Job / Artifacts。

Golden evidence 至少包含：

```text
calculation
drawing
bim / IFC
```

非 strict 模式忽略隨機 Job/Artifact ID 與 checksum；strict 模式要求 checksum 並比較。任何 ERROR、未閉合 TURN_END、Job 未到 review/completed/published、缺 calculation/drawing/BIM 都 fail closed。

真實 H8 驗證仍要求同一 Win11 runner / 同一 OS + specialist engine 環境跑 Native 與 Harness，避免硬體漂移污染時間與行為比較。

## H9 ComfyX long-running job

狀態：`IMPLEMENTED — REAL-GPU-MP4-PENDING`

新增：

```text
coworker/engineering/comfyx_long_job.py
tests/test_engineering_comfyx_long_job.py
```

已對齊 ComfyX 現有 model-facing CLI：

```text
comfyx.job.status
comfyx.job.cancel
```

ComfyX status contract：history 是 terminal authority；queue 是 queued/running authority；terminal status 可攜帶 artifacts。

H9 最終成功不再接受「completed」或「副檔名是 .mp4」作為證據。必須同時成立：

1. Engineering-OS Job = review/completed/published。
2. 不得是 cancelled/archived。
3. 至少一個 `animation_video` / `video/mp4` Artifact。
4. local artifact 是一般檔案且非空。
5. 前 64 bytes 有合理 ISO-BMFF `ftyp` box。
6. major brand 合法。
7. 本地 SHA256 必須等於 OS Artifact checksum。
8. 若有 `animation_comfyx_execution`，其 status 必須 succeeded。
9. cancelled Job 即使殘留舊影片也不可重用為成功證據。

真實 H9 VERIFIED 仍需要 RTX 本機 Action 真生成一個非空 MP4，最好再加 ffprobe/readability gate；目前不把 deterministic container test 說成真 GPU 生成。

## H10 Desktop packaging

狀態：`IMPLEMENTED — PACKAGE-BUILD-VERIFICATION-PENDING`

新增：

```text
coworker/runtimes/harness_packaging.py
tests/runtimes/test_harness_packaging.py
```

Tauri bundle 已新增：

```text
../../../harness → harness
```

production resolver 支援：

```text
OPENWORKER_HARNESS_ASSET_DIR
OPENWORKER_RESOURCE_DIR/harness
<packaged sidecar>/../harness
repo-root/harness (dev fallback)
```

它會驗證：

```text
upstream-lock.json
upstream-plugin/openworker-engineering-tools.ts
```

且不把 integration assets 誤當成完整 ACP runtime。官方 `@deepseek-ai/dsh-acp` 是 library package、依賴 Harness workspace peer services，並不是可直接當 Desktop externalBin 的單一 CLI，因此正式啟動仍要求 `OPENWORKER_HARNESS_COMMAND` 指向真可啟動 composition；缺 command 時 fail closed。

## H11 Default-runtime decision

狀態：`IMPLEMENTED — NATIVE REMAINS DEFAULT`

`coworker/runtimes/manager.py` 已鎖定：

```text
DEFAULT_RUNTIME = native
```

Harness 只能 explicit opt-in：

```text
OPENWORKER_HARNESS_ENABLED=1
OPENWORKER_HARNESS_COMMAND=<real ACP composition command>
```

且 H10 packaged capability 必須 ready，否則 `RuntimeUnavailableError`。

新增：

```text
tests/runtimes/test_runtime_h11_policy.py
```

這個決定不是認為 Harness 不可用，而是避免在 H8 真 RC A/B 與 H9 真 GPU MP4 尚未完成前，把產品預設切到新 runtime。NativeRuntime / TurnEngine 暫不刪除。

## H3-H11 統一 Win11 Gate

AI-Engineering-OS workflow：

```text
.github/workflows/openworker-harness-h3-official-win11.yml
name: OpenWorker Harness H3-H11 Official Win11
runs-on: [self-hosted, Windows, X64]
OpenWorker ref: 6460c6c26f6f4c611f71a885dcd3e826a189492e
DeepSeek Harness ref: 47f943859bef60e4160492346772ded9b24f765a
```

Gate 包含：

```text
H1-H7 runtime regressions
H8 runtime A/B oracle tests
H9 MP4/artifact tests
H10 packaging tests + Tauri resource config validation
H11 native-default / explicit-Harness policy tests
H2 TypeScript contracts
exact official Harness pin
official ACP initialize + session/new
official Cordis Engineering tool plugin smoke
H6.2 deterministic official Harness engineering-tool Golden E2E
```

## 目前 H0-H11 代碼狀態

```text
H0  architecture                              IMPLEMENTED
H1  AgentRuntime seam                         VERIFIED — WIN11
H2  Harness ACP-first skeleton                VERIFIED — WIN11
H3  real ACP subprocess runtime               VERIFIED — OFFICIAL ACP / WIN11
H4  permission / approval bridge              VERIFIED contract + H6 producer
H5  session ownership / resume boundary       IMPLEMENTED
H6  dynamic Engineering-OS tools              IMPLEMENTED
H6.1 official Cordis tool plugin              IMPLEMENTED
H6.2 deterministic real Harness agent loop    IMPLEMENTED
H7  jobs / interrupt / cancel                 IMPLEMENTED
H8  RC Native vs Harness A/B verifier         IMPLEMENTED — REAL-RC-A/B-PENDING
H9  ComfyX long job MP4 verifier              IMPLEMENTED — REAL-GPU-MP4-PENDING
H10 Desktop packaging capability              IMPLEMENTED — PACKAGE-BUILD-PENDING
H11 default-runtime decision                  IMPLEMENTED — NATIVE DEFAULT
```

因此「功能代碼」已推進到 H11；剩餘工作主要是驗證層：先把最新 H3-H11 Win11 gate 跑綠，再做 H8 真 RC 同機 A/B、H9 真 GPU MP4 與 H10 真 installer/package build。這些未取得實證前不標 VERIFIED。
