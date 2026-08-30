# 真正本機總控 vs GitHub Action：差異、根因、修復進度與驗收標準

日期：2026-08-19

## 1. 結論

本文件的判定標準只有一個：**Case 業務是否能在不依賴 GitHub Actions scheduler 的前提下，由本機總控持續排程、並行執行、記錄、查詢與回傳成果。**

GitHub repository 可以用來保存/更新程式碼；這不等於 GitHub Actions 執行 Case。真正需要禁止的是：用 workflow_dispatch、push workflow、self-hosted runner 去 kick Case、查 Case 狀態、搬 Case 成果或執行 Case business action。

目前根因已找出並已在源碼層逐項修復：

1. go-tool local-work 原本只有單一 claim loop，實際單工。
2. gtr-work-executor 原本單一同步 loop，實際單工。
3. OpenWorker Case controller 雖有 4-slot，但 `gtr-local-exec` 原本直接執行 capability，繞過 `:8848` durable queue。
4. `runtime_work_items` 原本只保存最新狀態，不能完整還原本機總控歷史。
5. Case 0005 的角色/場景 IMAGE 原本用 role batch，在單一 action 內用 for-loop 串行跑 asset，無法真正餵滿 4-slot。
6. 本機 self-update 原本只更新 `tool-runtime.exe`，即使 server 新了，agent/executor/localexec 仍可能是舊單工版本。
7. 系統原本沒有一個直接回答「這個工作到底送到 GitHub Actions 還是本機總控」的權威查詢。

截至本次更新，以上七項均已有源碼實作；**但源碼完成不等於 ODA 實機驗證完成**。最終只有 ODA 的真實 durable ledger、4-slot 同時工作證據與實體成果一致時，才能宣告真正本機總控成功。

---

## 2. GitHub Actions 與真正本機總控的差異

### 2.1 GitHub Actions

典型鏈：

```text
ChatGPT
  -> GitHub API / workflow_dispatch / push
  -> GitHub Actions scheduler
  -> self-hosted runner
  -> script / action
  -> workflow log / artifact
```

GitHub Actions 適合：

- 程式碼 CI
- 首次安裝或無本機控制通道時的一次性安裝
- 升級/repair
- 版本驗證

GitHub Actions **不應**作為：

- Case business scheduler
- Case bootstrap/kick
- Case status bus
- 本機 queue 查詢
- Case artifact return
- Case approval gate transport

只要「為了知道 Case 做到哪」還需要 dispatch workflow，就不能叫真正本機總控。

### 2.2 真正本機總控

目標鏈：

```text
ChatGPT / llama.cpp Coder
        |
        v
 go-tool-runtime :8848
        |
        +-- method/tool authority
        +-- Case control API
        +-- durable local-work queue
        +-- 4 claim slots
        +-- 4 execution slots
        +-- route truth query
        +-- append-only work event ledger
        +-- artifact list/download
        |
        v
 OpenWorker :8787
        |
        +-- CaseWorklist / DAG / approval gate
        +-- durable child jobs
        +-- process / PID / timeout / cancel / explain
        |
        v
 allowlisted local capabilities
```

正常 Case 業務執行時：

```text
GitHub Actions = 0 次
```

---

## 3. 真正未並行的根因

### 3.1 原因 A：gtr-work-agent 原本單工

舊流程：

```text
claim A
 -> 等 A terminal
 -> claim B
```

即使 OpenWorker 有 `max_workers=4`，`:8848` queue 自己仍只有一個 inflight action。

### 3.2 原因 B：gtr-work-executor 原本單工

舊 executor 同步呼叫：

```text
reg.Execute(A) -> 等完成 -> reg.Execute(B)
```

所以多 claim 也會被單一 executor 串行化。

### 3.3 原因 C：Case controller 與 go-tool queue 是兩套 scheduler

舊鏈：

```text
Case controller
 -> OpenWorker child job
 -> gtr-local-exec
 -> capability
```

`gtr-local-exec` 原本直接執行 capability，因此 `:8848` durable queue 根本不知道 Case action 正在跑。

### 3.4 原因 D：沒有完整 append-only 本機總控帳本

舊 `runtime_work_items` 是 current-state table：

```text
pending -> claimed -> completed
```

前一狀態被覆蓋；無法回答：

- 哪個 claim slot 接單
- 哪個 executor slot 真正執行
- PID 是多少
- heartbeat 時間
- lease 是否曾回收
- retry 是第幾次
- 何時真正完成/失敗

### 3.5 原因 E：0005 IMAGE 是 batch 內部串行，不是真 fan-out

舊 `image.comfyx.storyboard-real(role=character_master)` 會在 handler 內：

```text
for asset in assets:
    generate(asset)
```

所以即使 `0005-030` 與 `0005-040` 同時執行，最多也只是兩個大 action，不會形成多個獨立 durable work items。

### 3.6 原因 F：self-update 只更新 server，不更新 worker binaries

如果只更新：

```text
tool-runtime.exe
```

但不更新：

```text
gtr-work-agent.exe
gtr-work-executor.exe
gtr-local-exec.exe
```

則 server 雖然顯示新 API，實際執行仍可能是舊單工模式。

### 3.7 原因 G：缺少 execution route truth

過去很容易混淆：

```text
「這個工作有跑」
```

但不知道是：

```text
GitHub Actions runner 跑的
```

還是：

```text
:8848 本機 durable supervisor 跑的
```

因此需要路由真相 API，不能靠 commit、workflow UI 或名稱猜測。

---

## 4. 已完成的源碼修復

### 4.1 go-tool local-work 改為 4 claim slots

`gtr-work-agent` 現在使用 bounded worker pool：

```text
slot-01
slot-02
slot-03
slot-04
```

每個 slot 有獨立：

- worker_id
- claim
- lease
- heartbeat
- terminal wait

worker ID 形如：

```text
DESKTOP-ODAQN0D-pid-1234-slot-01
```

### 4.2 executor 改為 4 execution slots

`gtr-work-executor` 同樣為 4-worker pool。

每個 claim 使用 `.exec.lock` 防止同一 work 被兩個 executor slot 重複執行。

執行鎖會定期刷新；executor crash 後 stale lock 可回收，不再因 45~50 分鐘固定 stale window 長時間卡住。

### 4.3 gtr-local-exec 改成 durable queue compatibility client

現在：

```text
OpenWorker child job
 -> gtr-local-exec --claim ...
 -> POST :8848/api/execution/local-work
 -> 等 durable terminal
```

`gtr-local-exec` **不再直接執行 capability**。

因此既有 controller 不必全部重寫，也會自動進入真正 go-tool local supervisor。

### 4.4 本機 queue 支援 idempotent caller work_id

Case controller 可使用既有 `execution_id` 當 `work_id`。

同 work_id 重送：

- host/capability/inputs 完全相同 -> 返回原 durable work
- identity 不同 -> fail-closed conflict

避免 controller 重啟或 retry 生成重複 action。

### 4.5 append-only `runtime_work_events`

已新增 SQLite durable event ledger。

事件包括：

```text
submitted
claimed
heartbeat
lease_reclaimed
execution_started
execution_finished
execution_failed
completed
failed
```

`runtime_work_items` 繼續負責 current state；`runtime_work_events` 負責不可覆蓋歷史。

### 4.6 executor slot / PID 也進入 ledger

不能只記 claim slot。

executor 在 capability 前後會追加：

```text
execution_started
  executor_slot
  pid
  executor_id
  started_at

execution_finished / execution_failed
  executor_slot
  pid
  duration/error
```

而且必須持有該 work 目前有效的 `claimed_by + lease_token` 才能寫入，不能偽造別的 work 的執行歷史。

### 4.7 queue summary API

```text
GET /api/execution/local-work?assigned_host=DESKTOP-ODAQN0D
```

直接返回：

- max_parallel_actions
- active_slots
- free_slots
- pending
- claimed
- completed
- failed
- inflight
- queued

真實 4-slot 驗證至少要看到一次：

```text
active_slots >= 2
```

理想 fan-out 高峰：

```text
active_slots = 4
free_slots = 0
```

### 4.8 work event ledger API

按機器：

```text
GET /api/execution/local-work/events?assigned_host=DESKTOP-ODAQN0D
```

按工作：

```text
GET /api/execution/local-work/{work_id}/events
```

這是本機 Action 的完整歷史權威。

### 4.9 Windows installer 固定 4-slot 並固定工具 root

安裝契約明確：

```text
MaxParallelActions = 4
claim_workers = 4
execution_workers = 4
```

並明確傳入：

- OpenWorker root
- ComfyX root
- ComfyX-Studio root
- OpenMAIC root
- ComfyUI output root

不再依賴 SYSTEM 環境碰運氣。

### 4.10 full local self-update

`go-tool.runtime.update-local` 已由只更新一個 binary 改為 staging / upgrade 四個：

```text
tool-runtime.exe
gtr-work-agent.exe
gtr-work-executor.exe
gtr-local-exec.exe
```

流程：

1. 本機 checkout 先跑必要 Go tests。
2. 四個 binary 全部 staging build。
3. 全部算 SHA256。
4. update work 必須先 durable completed。
5. 才停止本機 Scheduled Tasks。
6. 備份並替換四個 binary。
7. 重啟 queue -> executor -> agent。
8. 驗證 `:8848/health`。
9. 失敗則四個 binary 全部 rollback。

因此首版 true-local runtime 裝上後，後續升級不再需要 GitHub Actions。

---

## 5. 「這個工作去了哪裡？」路由真相查詢

新增：

```text
GET /api/execution/route?id=<work-id-or-execution-id>
GET /api/execution/route?work_id=<work-id>
GET /api/execution/route?execution_id=<capability-id:github-run-id>
```

### 5.1 LOCAL_SUPERVISOR

若 `work_id` 存在於本機 `runtime_work_items`：

```json
{
  "resolved": true,
  "route": "local_supervisor",
  "route_label": "LOCAL_SUPERVISOR",
  "business_execution_authority": "go-tool-runtime-local-work-queue",
  "github_action_used_for_business_execution": false
}
```

這才是 Case 正常業務應出現的路由。

### 5.2 GITHUB_ACTIONS

若 `execution_id` 能解析為已註冊 `provider=github_actions` capability + GitHub run id：

```json
{
  "resolved": true,
  "route": "github_actions",
  "route_label": "GITHUB_ACTIONS",
  "business_execution_authority": "github-actions-execution-provider",
  "github_action_used_for_business_execution": true,
  "github_run_id": 123456
}
```

### 5.3 UNKNOWN

兩個 authority 都找不到則：

```json
{
  "resolved": false,
  "route": "unknown",
  "route_label": "UNKNOWN"
}
```

**路由查詢本身不呼叫 GitHub、不觸發 workflow。**

因此之後使用者問：

> 「這個工作是排到 GitHub Action 還是派到本機總控？」

應直接以此 API 回答，不准用 workflow UI 推測。

---

## 6. Case 0005 真正 4-slot fan-out

### 6.1 0005-030 / 0005-040

新增權威 controller：

```text
coworker.case0005_true_local_controller
```

角色圖與場景圖不再使用一個 role batch action 內部串行。

現在會把 `visual-assets/requirements.json` materialize 成 per-asset child work：

```text
0005-030 group
  -> character asset A local work
  -> character asset B local work
  -> character asset C local work
  -> ...

0005-040 group
  -> scene asset A local work
  -> scene asset B local work
  -> scene asset C local work
  -> ...
```

每個 child 都有：

- 獨立 work_id
- 獨立 OpenWorker child job
- 獨立 :8848 local-work record
- 獨立 claim slot
- 獨立 executor slot/PID
- 獨立 receipt
- 實體 image path
- SHA256

030 與 040 同時 ready 時，其所有 child work 共同競爭 ODA 的 4 個本機 slots。

### 6.2 0005-060

既有 per-shot video fan-out 繼續保留：

```text
shot-001
shot-002
shot-003
shot-004
...
```

每個 shot child 透過 compatibility `gtr-local-exec` 進入同一個 `:8848` durable queue，因此同樣受 4-slot supervisor 控制。

---

## 7. 雙層完整帳本

真正成功需要同時能看到兩層：

### A. Case orchestration ledger

```text
D:\AI-Work\jobs\0005-SNOW-WHITE\.openworker\case-supervisor-ledger.jsonl
```

記錄：

- bootstrap
- dispatch scan
- step dispatch
- fan-out child materialization
- OpenWorker durable ACK
- child running/pass/fail
- parent aggregate
- downstream
- approval gate

### B. go-tool action execution ledger

SQLite：

```text
runtime_work_items
runtime_work_events
```

記錄：

- submitted
- claim slot
- heartbeat
- lease reclaim
- executor slot
- PID
- execution start/finish/fail
- terminal state

兩層需以 `execution_id/work_id` 對得起來。

---

## 8. 真正本機總控的最終成功標準

**只完成代碼，不算成功。**

ODA 實機必須同時滿足：

1. `local-queue-authority.json` 顯示：
   - machine = `DESKTOP-ODAQN0D`
   - max_parallel_actions = 4
   - claim_workers = 4
   - execution_workers = 4
2. Case 0005 使用：
   - `coworker.case0005_true_local_controller`
3. Case business work 的 route query 全部返回：
   - `LOCAL_SUPERVISOR`
   - `github_action_used_for_business_execution=false`
4. fan-out 期間實際看到：
   - `active_slots >= 2`
   - 並留下多個不同 slot worker ID
5. 最好實證：
   - `active_slots=4`
   - `free_slots=0`
6. `runtime_work_events` 能還原每個 action：
   - submitted -> claimed -> execution_started -> heartbeat* -> execution_finished -> completed
   - 或完整 failure/retry/reclaim 路徑
7. ledger 內可看到不同 `executor_slot` / PID。
8. Case `.openworker/case-supervisor-ledger.jsonl` 能從 Case bootstrap 一直重放到成果/approval/delivery。
9. PPTX、圖片、MP4 等實體成果存在且：
   - 非空
   - SHA256 一致
   - reopen / decode / physical QC 通過
10. Case 正常工作期間：
   - **沒有 GitHub Actions business execution**
   - GitHub 只可出現在程式碼/版本升級紀錄

若其中任何一項缺少，不應宣告「真正本機總控成功」。

---

## 9. 現在的狀態

### 源碼層：已實作

- 4 claim slots
- 4 execution slots
- gtr-local-exec -> :8848 durable queue compatibility
- caller work_id idempotency
- queue summary
- append-only runtime_work_events
- executor slot/PID lifecycle events
- local Case status/control/artifact APIs
- LOCAL/GITHUB/UNKNOWN execution route query
- 四 binary local self-update
- 0005-030/040 per-asset fan-out
- 0005-060 per-shot fan-out
- Case append-only supervisor ledger

### 尚需實機證明

- ODA 安裝並實際運行上述最新四 binary runtime
- 使用 `coworker.case0005_true_local_controller` 重新接續 0005
- 用 route query 證明 Case child 是 LOCAL_SUPERVISOR
- 用 queue summary 證明同時 2~4 個 active slots
- 用 event ledger 證明不同 claim/executor slots
- 產出實體 Case 成果並與 ledger/SHA/QC 一致

這些實證完成後，才把狀態從：

```text
IMPLEMENTED — WAITING FOR REAL LOCAL VERIFICATION
```

改成：

```text
REAL LOCAL SUPERVISOR VERIFIED
```
