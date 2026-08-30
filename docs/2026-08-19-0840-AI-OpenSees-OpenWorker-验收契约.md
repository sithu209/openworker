# AI-OpenSees × OpenWorker 验收契约

更新时间：2026-08-19 08:40 +08:00

## 定位

OpenWorker 不重新实现结构分析，也不解析 Civil 私有字段。AI-OpenSees 的执行权威仍属于 `liuxb99/AI-OpenSees` 的 operator workflow；OpenWorker 负责读取工作状态与验收实体 evidence。

对应 go-tool capability：

`structural.ai_opensees.authority.analyze`

固定机器：`O87`

## 验收命令

Go runtime 新增：

`openworker-ai-opensees-evidence --workspace <workspace>`

默认输出：

`<workspace>/openworker-ai-opensees-evidence-report.json`

退出码：

- `0`：accepted=true
- `1`：evidence 被拒绝
- `2`：参数、JSON 输出或本机 I/O 错误

## OpenWorker 实体复核

validator 会重新读取：

- `operator-evidence.json`
- `analysis-result.json`
- `authority-runtime-state.json`

并重新计算 workspace 中 9 个关键 artifact 的 SHA256：

1. `analysis-result.json`
2. `analysis-geometry.json`
3. `analysis-deformed.obj`
4. `analysis.tcl`
5. `node_displacements.csv`
6. `node_reactions.csv`
7. `opensees.stdout.log`
8. `opensees.stderr.log`
9. `authority-runtime-state.json`

非日志 artifact 必须非空。

## 三方 identity 闭环

必须同时满足：

- capability ID = `structural.ai_opensees.authority.analyze`
- repository = `liuxb99/AI-OpenSees`
- hostname = `O87`
- operator receipt schema = `ai-opensees/operator-evidence/v0.1`
- result schema = `ai-opensees/analysis-result/v0.4`
- runtime schema = `ai-opensees/mct-authority-runtime-state/v0.1`
- receipt / result / runtime 的 authority generation 一致
- receipt / result / runtime 的 catalog root 一致
- receipt / result / runtime 的 entry count 一致
- result source SHA256 = receipt MCT SHA256
- geometry / OBJ / CSV 的 result SHA256 = receipt SHA256 = OpenWorker 本机重算 SHA256

任何一项不一致即 fail-closed。

## 队列阻塞处理

AI-OpenSees evidence validator 不创建新的队列机制。若 OpenWorker durable queue 阻塞，继续使用已有 `openworker-queue-drain-auto` 一键清队列能力，再重新执行拥有 workflow。

## REAL 验收边界

以下内容不能由单元测试代替：

- Civil 2016 真实 Export MCT；
- 真实 `*MATERIAL/*SECTION` authority package；
- O87 上 REAL OpenSees 可执行文件；
- self-hosted REAL workflow run；
- OpenWorker 对该 REAL workspace 返回 `accepted=true`。

在这些证据出现前，只能标记 SOFTWARE IMPLEMENTED，不能标记 REAL PRODUCTION READY。
