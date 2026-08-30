# OpenWorker 纯 Go 本机执行核心与三机多 Agent 调度设计

日期：2026-08-18
状态：P2 BATCH-4 IMPLEMENTED — MULTI-AUTHORITY / ENDPOINT RECEIPT / CONNECTIVITY HISTORY READY

## 1. 当前架构

OpenWorker Python 层负责案例、WorkLedger、知识、审核与上层 orchestration；纯 Go `openworker-node.exe` 负责本机 durable execution、三机 observation/routing/control。GitHub Action 只作为 transport / CI / evidence。`Action completed`、`cluster durable ACK`、`task succeeded` 必须严格区分。

## 2. 已完成主线摘要

目前已经具备：SQLite durable queue、4 worker slots、Action `_work` worktree、resource locks、真实 process supervisor、timeout/cancel/process-tree kill、drain/retry/recover、Windows Service、build identity、job event ledger、restart PID reconciliation、tool/GPU/capability inventory、15 秒 lease、UL7/ODA/O87 service bootstrap、Cluster Registry、capability/load-aware route、cluster_jobs、cluster_agents、agent_slot durable authority、remote durable submit、cluster job status/cancel/retry/drain、listen/advertise/peers 网络 contract、durable cluster dispatch/control ledger、Python adapter 与 go-tool cluster capability。

真实三机 network receipt 仍未取得，因此不宣称 REAL VERIFIED。

## 3. P2 Batch-4：Endpoint Config Durable Receipt

提交 `ff737779` 新增 `go-runtime/internal/store/cluster_connectivity.go`。

新增 durable table：

```text
cluster_endpoint_receipts
```

每次 OpenWorkerNode 启动会记录：

```text
node_id
machine
listen
advertise
peers
build_commit
recorded_at
```

`d6969060` 接入 node lifecycle；`4fa8bc6f` 修正 build commit typed snapshot。

因此以后不需要只看 SCM binPath 或 Action 输入来猜节点网络配置，SQLite 里有最新启动时的权威 receipt。

## 4. P2 Batch-4：Connectivity Durable History

新增：

```text
cluster_connectivity_history
```

每次 peer probe 记录：

```text
observer_node_id
target_endpoint
target_node_id
target_machine
ok
latency_ms
error
observed_at
```

`c2dc3955` 给 Cluster Controller 增加 ProbeObservation callback，并将 peer probe 改为最多 3 次短 backoff：

```text
attempt 1
-> 100 ms
attempt 2
-> 200 ms
attempt 3
```

短暂网络抖动不立即把 peer 判死；连续失败仍 fail-closed，node lease 会失效。

本批刻意只对 observation/query 做自动 retry。`job.retry` 这类具有状态转换语义的 destructive/control POST 不做盲目重复，避免第一次已成功但 response 丢失后第二次造成错误状态判断。

`9c4f1299` 增加 endpoint/connectivity durable round-trip test。

## 5. P2 Batch-4：Connectivity / Endpoint API

`02e66002` 新增：

```text
GET /v1/cluster/endpoints
GET /v1/cluster/connectivity?limit=200
```

因此 cluster authority 可以直接回答：

```text
当前节点启动时 advertise 是什么？
peers 配了什么？
最近 UL7 -> ODA 探测成功还是失败？
最近延迟多少？
哪一个 endpoint 连续失败？
```

`9f06c5cc` 同步 Python Control Plane：

```text
cluster_endpoints()
cluster_connectivity()
```

## 6. P2 Batch-4：Cluster Authority 不再单点依赖 O87

之前 go-tool 只有：

```text
openworker.cluster.control -> O87
```

本批新增三个等价 transport：

```text
openworker.cluster.control       -> O87 primary
openworker.cluster.control.ul7   -> UL7 fallback
openworker.cluster.control.oda   -> ODA fallback
```

OpenWorker commits：

- `8158842c`：统一 `scripts/openworker_cluster_control.ps1`；
- `fe361c29`：O87 改用统一 transport；
- `e63a1fb6`：UL7 fallback workflow；
- `bc1f1b2c`：ODA fallback workflow。

go-tool-runtime `6daa96c9` 写入 fallback 顺序：

```text
O87 unavailable
-> UL7
-> ODA
```

Authority fallback 只改变“从哪台 node 发 cluster control HTTP”，绝不改变：

```text
job_id
dispatch_id
fixed machine
required capabilities
```

因此 O87 离线不会把固定 UL7 的 job 漂到 ODA。

## 7. 统一 Cluster Control Operations

三台 authority workflow 都调用同一脚本，支持：

```text
status
capabilities
jobs
agents
job.status
job.cancel
job.retry
route
submit
queue.drain
dispatches
dispatch
control.events
endpoints
connectivity
```

这样三份 workflow 不再各自复制一大段 PowerShell switch，降低能力漂移风险。

## 8. Authority Fallback REAL 验证入口

`17589b09` 新增：

```text
.github/workflows/openworker-cluster-authority-fallback-verify.yml
```

分别在：

```text
O87 / DESKTOP-O87PJNR
UL7 / DESKTOP-UL7V2VV
ODA / DESKTOP-ODAQN0D
```

验证：

```text
COMPUTERNAME
local OpenWorkerNode health
/v1/cluster/status
/v1/cluster/endpoints
/v1/cluster/connectivity
```

只有三条 authority transport 都真实可调用，才可以宣称 cluster control 不再有 O87 单点。

## 9. 当前网络语义

```text
listen
= 本机 bind address

advertise
= 其他 node 应该访问我的 URL

peers
= 我主动观察的其它 node URLs
```

Self-probe 仍走 local listen/loopback，不绕 advertise；peer registry 保存 node status 自己声明的 advertise endpoint。

默认保持：

```text
127.0.0.1:8787
```

只有显式配置 LAN/Tailscale endpoint 才进入跨机模式，不会自动暴露所有网卡。

## 10. 当前 Cluster API

```text
GET  /v1/cluster/status
GET  /v1/cluster/capabilities
GET  /v1/cluster/route
GET  /v1/cluster/jobs
GET  /v1/cluster/jobs/{job_id}
GET  /v1/cluster/agents
POST /v1/cluster/jobs
POST /v1/cluster/jobs/{job_id}/cancel
POST /v1/cluster/jobs/{job_id}/retry
POST /v1/cluster/queue/drain
GET  /v1/cluster/dispatches
GET  /v1/cluster/dispatches/{job_id}
GET  /v1/cluster/control-events
GET  /v1/cluster/endpoints
GET  /v1/cluster/connectivity
```

## 11. 当前调度与失败知识铁律

- COMPUTERNAME 是 fixed machine 最终 authority；
- fixed machine 永不自动漂移；
- `machine=any` 只用于非 destructive route/submit；
- expired lease 不接新任务；
- advertise endpoint 必须来自 node 自己 status；
- self health 不依赖 advertise 网络；
- remote submit 必须 matching durable ACK；
- cluster cancel/retry 必须先定位 owning node；
- queue drain 必须明确 node 或 all；
- cluster dispatch ledger != final result ledger；
- connectivity history != 当前 lease；
- 历史成功不能覆盖当前 offline；
- authority fallback 不能改变业务路由语义；
- Action completed != job succeeded。

## 12. 当前 REAL 验收状态

代码已经 IMPLEMENTED，但仍缺：

1. UL7 / ODA / O87 的真实 advertise endpoint；
2. 三机双向 HTTP connectivity receipt；
3. 三个 authority fallback workflow 的真实 receipt；
4. ODA `DESKTOP-ODAQN0D` 最终 COMPUTERNAME receipt；
5. remote durable submit 的真实跨机 smoke；
6. 一台 node offline -> fallback authority 接管 -> node 恢复上线的真实 convergence receipt。

所以当前状态是：

**P2 Batch-4 IMPLEMENTED，不等于 REAL THREE-NODE HA VERIFIED。**

## 13. 下一批 P2

下一批优先补：

```text
cluster dispatch_id 跨 authority 去重/冲突验证
control operation request_id / idempotency receipt
connectivity current-state summary（不是只有 history）
authority selection helper
真实 Case 0002/0003/0004 cluster-aware migration
```

其中 fixed-machine 业务步骤仍保持 fixed；只有确实可在多机等价执行的步骤才使用 `machine=any + capability`。

## 14. 验收铁律

持续覆盖 multi-worker、resource lock、timeout/cancel/drain、restart PID recovery、SCM service、inventory/lease、agent_slot、job 聚合、remote ACK。P2 额外必须验证 advertise、endpoint receipt、connectivity history、peer backoff、lease expiry、三 authority transports、authority fallback 不改变 fixed machine，以及节点恢复上线后的 registry convergence。

## 15. 最终目标

OpenWorker 成为自己拥有的三节点、多 Agent、可并行、可恢复、可观察、可按 capability 选择节点、且没有单一 control transport 依赖的本机优先执行系统。GitHub Actions 只保留版本、入口、CI 与证据通道，不再承担长任务 scheduler。
