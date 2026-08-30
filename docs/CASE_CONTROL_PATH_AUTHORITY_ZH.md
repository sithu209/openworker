# Case 控制路径权威说明

更新时间：2026-08-19（Asia/Taipei）

## 一句话规则

> **流程问 OpenWorker；工具问 go-tool。**

这是给 ChatGPT、OpenCode、llama.cpp Coder 与其他 LLM/Agent 的 canonical control contract。大模型不得根据旧聊天记录自行猜测 Case 当前进度、下一 step 或 business capability。

## 唯一推荐架构

新版 Case 主控 authority 是 **Go 版 OpenWorker**，canonical executable：

`C:\ProgramData\OpenWorker\bin\openworker.exe`

相容入口：

`C:\ProgramData\OpenWorker\bin\openworkerctl.exe`

正确链路：

```text
ChatGPT / LLM
  -> 高阶短命令
  -> （无法直达时）GitHub transient short-command transport
  -> target machine openworker.exe / openworkerctl.exe
  -> OpenWorker Go Case Engine / Local Supervisor
  -> Case DAG / reconcile / READY / fanout
  -> go-tool-runtime :8848 durable local-work queue
  -> local claim workers (default 4)
  -> local executor slots (default 4)
  -> owning-tool capability
  -> durable result / execution ledger
  -> OpenWorker reconcile / fanout join / next READY
```

因此：

- `openworker.exe` = 新版 Go 主控 / Case controller / process authority；
- `openworkerctl.exe` = compatibility CLI / 短命令入口；
- `go-tool-runtime :8848` = 工具能力、durable queue、claim/executor 与 execution authority，不是 Case 流程主控；
- `OpenWorker :8787` = resident node / durable Case ledger authority；
- `COMPUTERNAME` = fixed-machine authority。

## 大模型必须先从 OpenWorker 得到什么

任何 Case 操作开始前，大模型必须优先取得 OpenWorker 的流程状态，而不是先询问工具：

1. Case 是否存在、固定机器与 workspace；
2. current step / current durable work_id；
3. current work 状态：pending / claimed / running / completed / failed；
4. 是否存在等待 review / approval 的 gate；
5. 是否允许 continue；
6. reconciliation 后有哪些 READY steps；
7. 若为 fanout，parent/child/join 当前状态；
8. 若失败，OpenWorker 记录的 leaf blocker。

只有当 blocker 或下一步涉及 capability contract、canonical inputs、executor、owning tool root、工具环境或 queue health 时，才转向 go-tool。

## Canonical short commands

```text
supervisor_status
case_status
case_work_status
case_bootstrap
case_continue
case_dispatch
queue_clear
```

### 大模型决策规则

- `pending / claimed / running`：只查询，不重复 `case_continue`。
- `completed`：由 OpenWorker reconcile，再由 OpenWorker 推进 READY step。
- `failed`：先相信 durable failure evidence；只修真实 leaf blocker。
- review gate：未取得用户/ChatGPT 明确 APPROVE 前，不跨 gate。
- 多个 READY steps：由 OpenWorker fanout，不由大模型手工开多个 business workflow。

## 本机并行执行的真实含义

新版所谓「本机 Action 并行」不是让 GitHub 同时跑多个长业务 workflow。

OpenWorker 负责 Case fanout；go-tool durable queue 承接 child works；本机 `gtr-work-agent` 与 `gtr-work-executor` 使用多个 slot 并行消费。默认目标是 4 claim + 4 executor slots。executor 最终通过本机 capability registry 执行 owning-tool capability。

因此业务并行的 authority 位于本机：

```text
OpenWorker fanout
  -> go-tool durable local-work queue
  -> N claim slots
  -> N executor slots
  -> owning-tool capabilities
  -> terminal results
  -> OpenWorker join/reconcile
```

GitHub 不拥有这些 business workers。

## GitHub 的正确边界

GitHub 可以在 ChatGPT 无法直接到达目标机时，作为**短命令瞬时 transport**：

```text
ChatGPT
  -> command-requests/<machine>.json
  -> short-lived GitHub Action
  -> target openworkerctl/openworker.exe
  -> local acceptance
  -> command-results/<machine>/<request_id>/final.json
  -> ChatGPT read-back
```

GitHub Action 一旦拿到本机 acceptance/短命令结果就必须结束。

允许：

- `supervisor_status`
- `case_status`
- `case_work_status`
- `case_continue`
- `case_bootstrap`
- `queue_clear`
- 安装、升级、修复 control-plane

禁止：

- GitHub Action 做 Case business execution；
- GitHub Action 等待整个 Case 完成；
- GitHub artifact 作为业务成果 authority；
- GitHub workflow 状态代替 OpenWorker durable ledger；
- PR -> control PR -> 多层 workflow 编排普通 Case 短命令；
- legacy Python controller 作为 Go-native Case controller；
- 大模型绕过 OpenWorker 直接拼 durable business work。

## go-tool 的正确询问时机

「工具问 go-tool」表示：

- 查询 capability 是否注册、能力边界与 canonical inputs；
- 查询 owning tool / root / environment；
- 查询 queue、claim worker、executor slot 健康；
- 查询 execution event / capability failure；
- 开发新 Case step 时，先确定工具 contract，再把 mapper 固化进 OpenWorker。

对于已经进入正式 Case DAG 且已有 action mapper 的步骤，大模型不应每一步重新手工选择工具；应让 OpenWorker `case_continue` 自动映射并 dispatch。

## Case 0005 当前特别规则

当前已存在 durable business work：

`case0005-0005-010-r000014-17b8b780`

因此在它 terminal 前：

- **不得再发新的 `case_continue`**；
- 只能发 `case_status` / `case_work_status` 查询；
- terminal completed 后由 Go Case Engine reconciliation 决定下一 READY step。

Case 0005 的 030/040 fanout 源码现已存在 `case0005_fanout.go`、`fanout_runtime.go` 及对应测试；它不再登记为「尚未实现的纯源码缺口」，后续要求的是 REAL ODA child-work 并行与 join 验收。

没有 local acceptance、CaseWorklist、durable work、append-only ledger 或真实 artifact 的直接证据，不得宣称 Case 已继续或完成。
