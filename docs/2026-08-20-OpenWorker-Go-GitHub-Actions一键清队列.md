# OpenWorker Go：GitHub Actions 一键清队列

日期：2026-08-20（Asia/Taipei）

## 目的

把过去依赖 GitHub Actions workflow + `gh api` 的“清 Actions 队列”方法，正式收进 OpenWorker Go 工具本体。以后大模型或管理员不需要修改 workflow 文件来触发清理。

## 两种队列必须严格区分

1. `openworkerctl queue clear [MACHINE]`
   - 清的是 go-tool / OpenWorker 本机 durable work 队列。
   - API：`POST /api/execution/local-work/clear`
   - 属于业务执行层。

2. `openworker-actions-queue-clear`
   - 清的是 GitHub Actions transport queue。
   - 直接使用 GitHub REST API。
   - 只处理 queued / in_progress / waiting / requested 等所有 `status != completed` 的 workflow runs。
   - 不代表业务完成，也不得改写业务状态。

## 新工具

源码：

`go-runtime/cmd/openworker-actions-queue-clear/main.go`

执行：

```powershell
go run ./cmd/openworker-actions-queue-clear -repo liuxb99/openworker
```

或编译后：

```powershell
openworker-actions-queue-clear.exe -repo liuxb99/openworker
```

Token 来源按优先顺序：

- `OPENWORKER_GITHUB_TOKEN`
- `GH_TOKEN`
- `GITHUB_TOKEN`
- `-token`

Token 必须拥有目标仓库 Actions write 权限。

## 行为

工具会：

1. 分页列出仓库全部 workflow runs。
2. 选出所有 `status != completed` 的 run。
3. 可用 `-exclude-run-id` 排除当前控制 run。
4. 对其余 run 调用 GitHub `POST /actions/runs/{run_id}/cancel`。
5. 默认每 2 秒重新检查。
6. 最长默认等待 90 秒。
7. 只有确认 remaining 为 0 才输出 `PASS` 并返回 exit code 0。
8. 若仍有 non-terminal run，输出 `FAIL` 并返回非 0。

输出 JSON 包含：

- `schema_version`
- `repository`
- `nonterminal_before`
- `cancelled_ids`
- `remaining_after`
- `outcome`
- `verified_at`

## 原则

GitHub Actions 这里只是 transport / deployment / diagnostic 层。即使 Actions queue 被清空，也不能当成 Case、durable work 或 artifact 已完成。业务 authority 仍是 OpenWorker / go-tool-runtime durable work ledger、claim/executor slot、artifact receipt。
