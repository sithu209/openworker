# OpenWorker「密语」Hook REAL 稳定性测试报告

> 日期时间：2026-08-19 19:26 +08:00（Asia/Taipei）
> Repo：`liuxb99/openworker`
> 目标机：`DESKTOP-ODAQN0D`
> Runner：`DESKTOP-ODAQN0D-R001`
> 结论：REAL STABILITY PASS — 27 / 27

## 1. 本轮加固内容

本轮先固定代码，再做重复 REAL 测试，避免边改边测污染结论。

### 1.1 Runner Hook

`scripts/openworker-job-started-hook.ps1`

新增：

- `OPENWORKER_CONTROL` 无值时严格 passthrough；
- schema / request_id / command / machine / max_parallel fail-closed；
- 固定 allowlist：`CASE.STATUS`、`CASE.CONTINUE_BATCH`、`SUPERVISOR.STATUS`、`QUEUE.CLEAR`；
- 结构化 Hook receipt；
- 失败分类；
- dispatcher 结果嵌入 Hook receipt；
- 继续禁止任意 shell payload。

Hook receipt 目录：

`C:\ProgramData\OpenWorker\hooks\receipts`

### 1.2 Control Envelope Dispatcher

`scripts/invoke-openworker-control-envelope-v1.ps1`

新增：

- `request_id` durable receipt；
- 同 request_id 幂等命中；
- 30 秒默认超时；
- native process exit code 可靠捕获；
- stdout / stderr 分离；
- `go_tool_unreachable`、`timeout`、`openworker_process_failed`、`invalid_control_output` 分类；
- GitHub 仍只标记为 command transport，绝不标记 business execution。

Dispatcher receipt 目录：

`C:\ProgramData\OpenWorker\control-envelope\receipts`

### 1.3 稳定性 Harness

新增：

`scripts/test-openworker-embedded-control-stability.ps1`

每轮固定执行：

- `CASE.STATUS` × 5；
- `SUPERVISOR.STATUS` × 2；
- 同一 request_id 的 `CASE.STATUS` × 2，检查幂等；
- 总计 9 个控制调用。

所有调用均为只读控制，不推进 Case business step。

## 2. REAL 测试结果

### Run 1

GitHub Actions run：`32247228449`

结果：

- total_rounds = 9
- successful_rounds = 9
- 成功率 = 100%
- 单轮延迟约 457–634 ms

### Run 2

GitHub Actions run：`32247292088`

结果：

- total_rounds = 9
- successful_rounds = 9
- 成功率 = 100%
- 单轮延迟约 485–659 ms

### Run 3

GitHub Actions run：`32247344666`

结果：

- total_rounds = 9
- successful_rounds = 9
- 成功率 = 100%
- 单轮延迟约 473–621 ms

### 汇总

```text
总调用：27
成功：27
失败：0
成功率：100%

CASE.STATUS          PASS
SUPERVISOR.STATUS    PASS
重复 request_id      PASS
Hook detection       PASS
OpenWorker dispatch  PASS
go-tool :8848 path   PASS
```

## 3. 已证明的 REAL 链路

```text
GitHub workflow
  ↓
ODA self-hosted runner
  ↓
OPENWORKER_CONTROL
  ↓
OpenWorker Job Hook
  ↓
Control Envelope dispatcher
  ↓
openworker.exe
  ↓
go-tool :8848 Local Supervisor
  ↓
OpenWorker / supervisor status result
```

日志在每轮均出现：

```text
[OpenWorker Hook] OPENWORKER_CONTROL detected
[OpenWorker Hook] control envelope accepted by OpenWorker
```

因此「GitHub Action 只夹带密语；OpenWorker 认识就执行」已从概念验证进入重复 REAL 稳定验证通过阶段。

## 4. 当前结论

这套方案现在可以作为正式控制入口候选。

当前已经证明的是只读控制面稳定：

- `CASE.STATUS`
- `SUPERVISOR.STATUS`
- request idempotency

下一层仍应分开验证：

1. `QUEUE.CLEAR` 一键清队列；
2. `CASE.CONTINUE_BATCH` 的 active-work 不重复提交；
3. Case-defined fanout 时 4 claim + 4 executor；
4. Runner Hook 安装到 `ACTIONS_RUNNER_HOOK_JOB_STARTED` 后，不在 workflow step 显式调用 Hook 的真正自动拦截。

只有以上四项也通过后，才把 Embedded Control v1 标记为完整生产闭环。
