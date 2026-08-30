# OpenWorker Control Envelope 批次並行控制協定 v1

> 日期：2026-08-19（Asia/Taipei）
> 狀態：DESIGN + IMPLEMENTATION START
> 適用：ChatGPT / GitHub Action / MCP / 本機 CLI → OpenWorker → go-tool-runtime

## 1. 問題背景

目前 GitHub Action 被用來逐條傳遞 `case_status`、`case_continue`、`case_work_status` 等控制命令。這種做法有兩個問題：

1. GitHub Action 是 transport / CI runner，不應理解 Case 業務流程。
2. 一次 Action 只傳一個細粒度命令，會讓 LLM 過度微操本機 Case Engine，也無法充分利用 OpenWorker + go-tool 的 4-slot 本機並行能力。

因此本版新增一個高階控制語言：**一個 GitHub Action 只送一個 Control Envelope；OpenWorker 收到後自己依 Case dependency / READY state / 本機可用 slot 決定實際要派哪些 work。**

## 2. 核心原則

### 2.1 GitHub Action 只做 transport

GitHub Action 不允許：

- 判斷 Case 下一個 business step；
- 直接執行 Case business capability；
- 自行拆解 030/040 等 fanout；
- 取代 OpenWorker 的 dependency / reconcile / join；
- 取代 go-tool durable local-work queue。

GitHub Action 只允許：

1. 驗證 Control Envelope 基本欄位；
2. 把 Envelope 交給固定機器上的 OpenWorker；
3. 回傳 ACK / result receipt。

### 2.2 OpenWorker 是流程 authority

OpenWorker 負責：

- Case state；
- dependency legality；
- READY work discovery；
- reconcile；
- fanout / join；
- blocker；
- 下一個合法 transition。

### 2.3 go-tool 是執行 authority

go-tool-runtime 負責：

- durable local-work queue；
- claim；
- executor；
- capability execution；
- execution evidence；
- 4 claim slots + 4 executor slots。

## 3. 新控制命令

第一版加入：

```text
CASE.CONTINUE_BATCH
```

CLI 對應：

```text
openworkerctl case continue-batch <CASE_ID>
```

語意：

> 請 OpenWorker 針對指定 Case 完成 reconcile，找出目前所有合法 READY work，並在本機最多 4 路並行限制下派送；若只有 1 個 READY work，就只派 1 個；若 0 個 READY work，應回報原因，不得由 transport 猜測下一步。

## 4. Control Envelope v1

建議 transport payload：

```json
{
  "schema": "openworker.control-envelope.v1",
  "request_id": "20260819-xxxx",
  "machine": "DESKTOP-ODAQN0D",
  "command": "CASE.CONTINUE_BATCH",
  "case_id": "0005",
  "policy": {
    "max_parallel": 4,
    "fail_closed": true,
    "join": "case-defined"
  }
}
```

### 欄位規則

- `request_id`：唯一；禁止重放相同 request id。
- `machine`：必須與本機 hostname / assigned_host 一致。
- `command`：只允許 allowlist。
- `case_id`：由 OpenWorker manifest/spec 再驗證一次。
- `max_parallel`：v1 最大值固定 4；transport 不得要求超過本機 supervisor contract。
- `fail_closed=true`：Case dependency / supervisor / manifest 任一 authority 驗證失敗即拒絕。
- `join=case-defined`：join 規則由 Case Engine 決定，不由 GitHub Action 指定業務語意。

## 5. 執行鏈

```text
ChatGPT
  ↓
1 個 GitHub Action / MCP / CLI Control Envelope
  ↓
OpenWorker Control CLI / API
  ↓
CASE.CONTINUE_BATCH
  ↓
OpenWorker reconcile + READY discovery
  ↓
最多 4 個合法 work
  ↓
go-tool durable queue
  ↓
4 claim slots + 4 executor slots
  ↓
terminal evidence
  ↓
OpenWorker reconcile / fanout join
  ↓
Control result
```

## 6. 重要限制

### 6.1 不是「硬塞四件 capability」

v1 不允許 LLM / GitHub Action直接提供四個 capability 讓總控照做。原因是這會繞過 Case dependency authority。

正確做法是：

```text
CASE.CONTINUE_BATCH(case_id=0005, max_parallel=4)
```

由 OpenWorker 自己決定當前 0~4 個合法 READY work。

### 6.2 不重複提交 running work

若 current work 已是 `pending / claimed / running`，OpenWorker 應以既有 durable state 為 authority，不得因再次收到 `CASE.CONTINUE_BATCH` 而建立重複 business work。

### 6.3 4-slot 是上限，不是必須填滿

- READY=1 → 只用 1 slot。
- READY=2 → 最多 2 slots。
- READY>=4 → 最多 4 slots。
- 其餘 work 留在 durable queue / 後續 reconcile。

## 7. 回傳格式

建議結果至少包含：

```json
{
  "schema": "openworker.control-result.v1",
  "request_id": "...",
  "accepted": true,
  "command": "CASE.CONTINUE_BATCH",
  "case_id": "0005",
  "machine": "DESKTOP-ODAQN0D",
  "dispatch": {
    "ready_count": 2,
    "dispatched_count": 2,
    "max_parallel": 4
  },
  "local_supervisor": {
    "claim_slots": [],
    "executor_slots": [],
    "active_slots": 2,
    "free_slots": 2
  }
}
```

實際 Case Engine response 可以包含更多欄位，但不得少掉 machine / case / command / dispatch outcome / supervisor evidence。

## 8. Case 0005 驗證方式

Case 0005 目前 `0005-010` 尚未有新的 terminal durable evidence，因此第一個 REAL 驗證必須遵守：

1. 先執行 `case status 0005`；
2. 若 `0005-010` 仍 pending/claimed/running：不得重複派工；`continue-batch` 必須 fail-closed 或回 existing-work 狀態；
3. 若 `0005-010` terminal completed：由 OpenWorker reconcile 後自行決定下一個 READY step；
4. 到 Case-defined fanout 時，才能驗證一個 `CASE.CONTINUE_BATCH` 是否自動派出多個合法 child work；
5. 回報必須同時列出 4 claim slots、4 executor slots、queue 與 leaf blocker。

## 9. 第一版實作範圍

本批只做最小閉環：

- `openworkerctl case continue-batch <CASE_ID>`；
- payload 帶 `max_parallel=4` 與 `control_mode=case_ready_batch`；
- 仍呼叫 OpenWorker Case dispatch endpoint，由 Case Engine 維持 authority；
- 不在 controlcli 實作 capability fanout；
- 不讓 GitHub Action直接執行 business work；
- 加單元測試保證 batch payload 與 fail-closed 行為。

## 10. 後續

v1 驗證成功後，再把 GitHub transport 的 allowlist 加入 `case_continue_batch`，讓一次 Action 指令可直接送進總控。之後同一個 Control Envelope 可被 MCP / Cloudflare / LAN CLI 共用，transport 可替換而不改 Case Engine 控制語言。
