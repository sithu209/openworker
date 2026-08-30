# OpenWorker Embedded Control「密語」Runner Hook v1

> 日期時間：2026-08-19 18:46 +08:00（Asia/Taipei）
> 最近更新：2026-08-19 19:12 +08:00（Asia/Taipei）
> 狀態：IMPLEMENTED — REAL HOOK RECOGNITION PROVEN / LOCAL SUPERVISOR RECOVERY IN PROGRESS
> Repo：`liuxb99/openworker`
> 目標機器：`DESKTOP-ODAQN0D`

## 1. 核心想法

GitHub Action 不需要理解 OpenWorker 業務語意，也不需要每一支 workflow 都加入一套 `if/switch/PowerShell` 控制邏輯。

只約定一個 GitHub 合法的「夾帶欄位」：

```yaml
env:
  OPENWORKER_CONTROL: >-
    {"schema":"openworker.control-envelope.v1","request_id":"demo-001","command":"CASE.CONTINUE_BATCH","machine":"DESKTOP-ODAQN0D","case_id":"0005","policy":{"max_parallel":4,"join":"case-defined","fail_closed":true}}
```

GitHub 對 `OPENWORKER_CONTROL` 只視為普通環境變數字串，不理解其中的 Case / command / fanout 語意。真正理解密語的是 self-hosted runner 上的 OpenWorker Job Hook。

## 2. 一次安裝、所有 workflow 共用

GitHub self-hosted runner 支援：

```text
ACTIONS_RUNNER_HOOK_JOB_STARTED=<absolute path>
```

當 job 已分配給 runner、但 workflow steps 尚未開始時，runner 會自動執行本機 hook。

固定入口：

```text
ACTIONS_RUNNER_HOOK_JOB_STARTED=C:\ProgramData\OpenWorker\hooks\openworker-job-started.cmd
```

之後所有跑到這台 runner 的 workflow 都自動經過同一個 hook。

## 3. 密語規則

### 3.1 沒有密語

若 job 沒有 `OPENWORKER_CONTROL`，Hook 必須 `exit 0`，不得改變原 workflow 行為。

### 3.2 有密語

Hook 讀取 `OPENWORKER_CONTROL`，解析為 `openworker.control-envelope.v1`，再交給本機 OpenWorker。

```text
GitHub job
  ↓
ACTIONS_RUNNER_HOOK_JOB_STARTED
  ↓
OPENWORKER_CONTROL ?
  ├─ 無 → exit 0 → 原 GitHub job 照常執行
  └─ 有
      ↓
   validate envelope
      ↓
   OpenWorker control dispatcher
      ↓
   Case Engine / supervisor
      ↓
   go-tool durable queue
      ↓
   最多 4 個本機 claim/executor slots
```

## 4. 責任邊界

### GitHub Action

只負責正常 workflow 執行與可選擇夾帶 `OPENWORKER_CONTROL` 字串，不負責 Case dependency、READY step、fanout/join、capability 選擇、durable queue 或本機 4-slot 排程。

### Runner Hook

只負責判斷有無密語、基本 schema/JSON 驗證、將 Control Envelope 交給 OpenWorker、回傳 dispatcher exit code。Hook 不允許自行執行任意 CMD / PowerShell business payload。

### OpenWorker

負責 allowlist command、machine/case 驗證、reconcile、READY discovery、dependency legality、fanout/join、leaf blocker、idempotency 與 business control authority。

### go-tool-runtime

負責 durable local-work queue、claim、executor、capability execution、execution evidence、4 claim slots + 4 executor slots。

## 5. 第一版允許命令

```text
CASE.STATUS
CASE.CONTINUE_BATCH
SUPERVISOR.STATUS
QUEUE.CLEAR
```

任何未知命令：`REJECT / non-zero exit`，不得猜測。

## 6. CASE.CONTINUE_BATCH 語意

```json
{
  "schema": "openworker.control-envelope.v1",
  "request_id": "case0005-batch-001",
  "command": "CASE.CONTINUE_BATCH",
  "machine": "DESKTOP-ODAQN0D",
  "case_id": "0005",
  "policy": {
    "max_parallel": 4,
    "join": "case-defined",
    "fail_closed": true
  }
}
```

OpenWorker 收到後：reconcile durable state；active work 不重複提交；找合法 READY step；Case 定義允許 fanout 時建立 child works；投遞 go-tool durable queue；本機 supervisor 最多 4 路並行；join/acceptance/blocker 仍由 Case authority 判斷。

`max_parallel=4` 是上限，不代表一定要同時有四件合法 work。

## 7. 安全原則

- 密語不是 shell script。
- 禁止任意 PowerShell/CMD/executable path。
- `command` 必須 allowlist。
- `machine` 必須與 runner 實機一致。
- `request_id` 必須合法並可供 idempotency 使用。
- `max_parallel` 固定 1..4。
- `fail_closed` 預設 true。
- Hook 只呼叫固定 OpenWorker dispatcher。
- OpenWorker/go-tool 才有 business authority。

## 8. 已完成實作

已合併至 `main`：

1. `scripts/openworker-job-started-hook.ps1`：無密語 passthrough；有密語做 JSON/schema/request_id/command/machine/max_parallel 驗證；未知命令 fail-closed；合法後呼叫 `invoke-openworker-control-envelope-v1.ps1`。
2. `scripts/openworker-job-started.cmd`：Windows runner 固定 Job Hook entrypoint。
3. `scripts/install-openworker-runner-hook.ps1`：安裝到 `C:\ProgramData\OpenWorker\hooks`，並寫 runner `.env`。
4. `.github/workflows/smoke-openworker-embedded-control.yml`：無密語 passthrough smoke + `CASE.STATUS` recognized-secret smoke。
5. `scripts/recover-case0005-local-supervisor.ps1`：ODA local supervisor 自動恢復器。

## 9. REAL 測試證據

### 9.1 第一次真正進入 ODA runner

Smoke run：`32245884480`。

Runner 實機：

```text
Runner name: DESKTOP-ODAQN0D-R001
Machine name: DESKTOP-ODAQN0D
```

第一次 recognized-secret smoke 因 Windows ExecutionPolicy 阻擋 GitHub 產生的臨時 `.ps1` 而失敗，尚未進入 Hook 本體。Smoke 已改成 `cmd → powershell.exe -ExecutionPolicy Bypass -File ...`，與正式 `.cmd` hook 入口一致。

### 9.2 密語識別已取得 REAL 證據

第二輪 smoke run：`32245959014`。

ODA log 明確出現：

```text
[OpenWorker Hook] OPENWORKER_CONTROL detected
```

並且 Hook 已成功進一步呼叫本機 `openworker.exe`。因此以下鏈路已由實機證明：

```text
GitHub workflow
→ ODA self-hosted runner
→ OPENWORKER_CONTROL
→ Hook parser
→ OpenWorker dispatcher
→ openworker.exe
```

失敗點已經在下一層：

```text
127.0.0.1:8848 connect actively refused
```

即 go-tool local supervisor 當時沒有監聽；這不是密語 parser 失敗。

### 9.3 Recovery 實測抓出的缺口

Recovery run `32246176631` 證明舊 go-tool 安裝器/checkout 與當前 OpenWorker root 不一致，並抓到 activation script 舊式 `throw'...'` 寫法的 PowerShell 解析缺口。

後續 recovery run `32246317765` 已進一步證明：

```text
refuse to overwrite dirty go-tool checkout
```

也就是 ODA 上固定 go-tool checkout 有本機修改/生成物；舊恢復策略為 fail-closed，因此無法自動更新到 `origin/main`。

## 10. Dirty checkout 的正式恢復政策

穩定性不能建立在 `git reset --hard` 靜默丟資料上，因此 recovery v2 改成「先保全、再恢復」。

固定流程：

1. 驗證 host 必須是 `DESKTOP-ODAQN0D`。
2. 驗證 checkout 必須存在 `.git`。
3. 驗證 `origin` 必須是 `liuxb99/go-tool-runtime`。
4. 若乾淨，直接同步 `origin/main`。
5. 若 dirty：
   - 保存 `git status --porcelain=v1 -uall`；
   - 保存 worktree binary patch；
   - 保存 staged binary patch；
   - 完整複製 untracked files；
   - 寫 manifest，包含 head/branch/origin/count/timestamp；
   - 保存位置：`C:\ProgramData\OpenWorker\recovery-backups\go-tool-runtime-<timestamp>`。
6. 保全完成後才允許 `git reset --hard` + `git clean -fd`。
7. `git fetch origin main`。
8. `git checkout -B main origin/main`。
9. 再驗證 checkout 必須完全乾淨。
10. 才執行 Case0005 local supervisor reinstall/REAL verification。

這樣 recovery 能自動化，同時任何本機修改都有可追溯備份，不會靜默遺失。

## 11. 穩定性驗收矩陣

本方案不是一次成功就算完成，至少要連續驗證以下項目：

### A. Passthrough

無 `OPENWORKER_CONTROL` 的普通 job 應連續成功，Hook 不應干擾 GitHub 原工作。

### B. Recognized-secret

連續多輪 `CASE.STATUS`：

- 每輪都要看到 Hook detection；
- 每輪都要進 OpenWorker；
- 不建立重複 business work；
- request_id 每輪唯一；
- result 必須是 JSON；
- 不允許偶發 shell/ExecutionPolicy 錯誤。

### C. Local supervisor

每輪狀態都必須包含：

- queue health；
- claim slots 1–4；
- executor slots 1–4；
- fresh claim count >= 4；
- fresh executor count >= 4；
- active/free summary；
- recent heartbeat；
- `github_action_used_for_business_execution=false`。

### D. Queue clear

`QUEUE.CLEAR` 後必須重新查 supervisor/queue，不能只相信 command exit code。

### E. Fail-closed

未知 command、錯 machine、非法 schema、非法 max_parallel 都必須拒絕，且不得執行任意 business payload。

### F. Recovery

即使 go-tool checkout dirty 或 supervisor 掉線：

- recovery 先備份再 reset；
- 8848 必須恢復；
- supervisor 必須重新 REAL_VERIFIED；
- 4+4 slots 必須重新 fresh；
- Case bootstrap/runtime route 必須恢復為 LOCAL_SUPERVISOR。

## 12. Case0005 最終穩定性測試順序

```text
recover 8848
→ verify OPERATIONAL / REAL_VERIFIED
→ QUEUE.CLEAR
→ verify queue empty + 4+4 fresh slots
→ CASE.STATUS smoke #1
→ CASE.STATUS smoke #2
→ CASE.STATUS smoke #3
→ 安裝正式 runner Job Hook
→ restart runner
→ 純夾帶密語 smoke（workflow steps 不手動呼叫 Hook）
→ CASE.CONTINUE_BATCH
→ 驗證 active work 不重複 / READY fanout 合法 / 4-slot evidence
```

其中 `CASE.CONTINUE_BATCH` 只在 status 證明 Case 狀態允許後才執行。

## 13. 目前 REAL 狀態

```text
中文規格                         COMPLETE
Control Envelope v1               COMPLETE
Job Hook parser/validator         COMPLETE
Windows hook entrypoint           COMPLETE
一次性 installer                  COMPLETE
GitHub → ODA runner               REAL PROVEN
OPENWORKER_CONTROL detection      REAL PROVEN
Hook → OpenWorker dispatcher      REAL PROVEN
OpenWorker → openworker.exe       REAL PROVEN
go-tool :8848                     RECOVERY REQUIRED
Dirty checkout preservation       IMPLEMENTED
4 claim + 4 executor REAL verify  PENDING RECOVERY
QUEUE.CLEAR REAL verify            PENDING RECOVERY
CASE.STATUS repeated stability    PENDING RECOVERY
Runner .env automatic hook        NOT YET INSTALLED
CASE.CONTINUE_BATCH stability     NOT YET TESTED
```

## 14. 結論

使用者提出的概念已由 ODA 實機證明成立：

> **GitHub Action 只夾帶 `OPENWORKER_CONTROL`；Runner Hook 只識別/轉交；OpenWorker 才解讀密語；go-tool 才做 durable queue 與本機並行。**

目前剩餘工作不是重做密語設計，而是把 ODA local supervisor 恢復鏈與 runner 自動 Hook 安裝做成可重複、可恢復、可觀測的穩定閉環。