# OpenWorker 本机 Coder Supervisor Agent 架构设计

日期：2026-08-18 12:52 +08:00  
状态：DESIGN — CHATGPT GLOBAL SUPERVISOR / LOCAL CODER SUPERVISOR CONTRACT

## 1. 背景

OpenWorker 已逐步从“GitHub Actions 驱动本机工作”演进为本机优先、多节点、多 Agent 的 durable execution system。

目前已经具备 SQLite durable queue、4 worker slots、Git worktree 隔离、resource locks、process supervisor、heartbeat、timeout/cancel/process-tree kill、drain/retry/recover、Windows Service、job event ledger、restart PID reconciliation、tool/GPU/capability inventory、Cluster Registry、UL7/ODA/O87 三节点、node lease、cluster jobs/agents、remote durable submit、cluster job status/cancel/retry/drain、Python Control Plane adapter、go-tool cluster capability 与 multi-authority cluster control。

因此 OpenWorker 已经具备作为“本机 Agent 执行作业系统”的主要基础。

下一阶段不需要重新设计 scheduler，而是正式定义两层 Supervisor：

```text
ChatGPT
= Global Supervisor

Local llama.cpp Coder
= Local Supervisor Agent

OpenWorker Python
= Control Plane / Business Orchestration

OpenWorker Go
= Durable Execution Kernel

go-tool
= Supervisor Tool/API Surface

Knowledge Graph
= Tool Knowledge / Failure Knowledge / Experience

GitHub Actions
= Transport / CI / Evidence
```

核心原则：

> 大模型负责思考、规划、判断与决策；OpenWorker 负责可靠执行、持久状态、资源管理与恢复。

> LLM context 永远不能成为 job state 的唯一 authority。

---

## 2. ChatGPT 现在即可作为 Global Supervisor

当前架构已经允许 ChatGPT 直接作为全局主控，不需要等待本机 Coder Supervisor 完成后才能工作。

ChatGPT 可以通过 go-tool / OpenWorker Cluster Control：

```text
查看 UL7 / ODA / O87 节点状态
查看 cluster jobs
查看 cluster agents
查看 capabilities
查看 fixed-machine job 状态
查看 failed / blocked / stale jobs
查看 dispatch / control receipts
执行 submit / status / cancel / retry / drain
查看 artifact / QC 结果
决定案例下一步
```

因此当前推荐结构是：

```text
                 ChatGPT
           Global Supervisor
                  |
                  v
          OpenWorker Cluster
          /       |       \
        UL7      ODA      O87
         |        |        |
     workers   workers   workers
```

ChatGPT 负责：

```text
跨案例规划
跨机器观察
全局优先级
业务流程判断
成果审核
QC 决策
是否返工
是否继续下一阶段
重大失败处置
```

OpenWorker 负责提供事实与执行能力。

ChatGPT 不应直接把 GitHub Action 页面当作真实任务状态来源。

必须保持：

```text
Action completed
!=
job succeeded
```

ChatGPT 判断任务真实状态时，应以 OpenWorker durable job state、event ledger、artifact receipt 与 QC receipt 为准。

---

## 3. Local Coder 是后续的 Local Supervisor，而不是取代 ChatGPT

未来每台机器可以再增加本机 llama.cpp Coder：

```text
                  ChatGPT
             Global Supervisor
                    |
                    v
            OpenWorker Cluster
        +-----------+-----------+
        |           |           |
        v           v           v
   UL7 Coder    ODA Coder    O87 Coder
   Supervisor   Supervisor   Supervisor
        |           |           |
        v           v           v
 OpenWorkerNode OpenWorkerNode OpenWorkerNode
        |           |           |
     A01-A04      A01-A04      A01-A04
```

两层 Supervisor 职责不同。

ChatGPT：

```text
Global Supervisor
跨案例
跨节点
全局业务目标
成果审核
质量控制
重大决策
```

Local Coder：

```text
Local Supervisor
高频观察本机状态
本机多个 jobs 调度
本机错误恢复
工具操作
读取 failure receipt
根据 Knowledge Graph 选择下一步
```

Local Coder 不取代 ChatGPT。

ChatGPT 也不需要等待 Local Coder 才能成为主控。

---

## 4. 单机 Local Supervisor 架构

每台机器可以有一个 Local Supervisor Coder：

```text
             llama.cpp
                 |
          Local Coder Model
                 |
                 v
        Supervisor Agent
                 |
        go-tool / OpenWorker API
                 |
                 v
        openworker-node.exe
                 |
      +----------+----------+
      |          |          |
     A01        A02        A03        A04
      |          |          |          |
    Coding      Test      Blender     ComfyX
```

Coder 是 Supervisor。

A01～A04 是 execution slots。

两者不得混为同一概念。

---

## 5. Supervisor 不直接管理 Windows Process

禁止把本机 Coder 设计成：

```text
Coder
  |
PowerShell
  |
Start-Process
  |
等待程序
  |
自己记住 PID
```

这种方式会导致：

- Coder crash 后失去工作状态；
- context reset 后不知道之前做到哪；
- PID / timeout / cancel 难以可靠管理；
- 多 Agent 容易互相踩 workspace；
- GPU / Blender / ComfyX 等共享资源容易冲突；
- Coder 等待长工作时无法继续处理其他任务。

正确模式：

```text
Coder / ChatGPT
      |
submit intent
      |
      v
OpenWorker durable job
      |
durable ACK
      |
Supervisor 继续处理其他事情
```

真实 process lifecycle 全部由 OpenWorker Go Core 管理。

---

## 6. Supervisor 的主要工作

Supervisor 负责：

1. 理解当前目标；
2. 查询 jobs；
3. 查询 worker slots；
4. 查询 tool / GPU / capability；
5. 查看 job events；
6. 判断 job 是否正常；
7. 查看 failed / blocked / stale 工作；
8. 查询 Knowledge Graph；
9. 查询工具负面知识；
10. 决定下一步 action；
11. submit 新 job；
12. cancel / retry 必要工作；
13. 在长工作执行期间继续处理其他工作；
14. 收到 artifact / QC 状态后决定下一步。

Supervisor 不负责：

```text
自己维护 durable queue
自己维护 PID
自己实现 resource lock
自己管理 process tree
自己猜 machine availability
自己猜 job 是否完成
把 context memory 当成 execution state
```

---

## 7. 非阻塞 Supervisor Loop

Supervisor 正常循环：

```text
observe
   |
   v
reason
   |
   v
decide
   |
   v
submit / control
   |
   v
durable ACK
   |
   +-------------------+
   |                   |
   v                   |
处理其他工作             |
   |                   |
   v                   |
重新 observe <----------+
```

例如：

```text
A01 -> 修改 ComfyX
A02 -> Go test
A03 -> Blender render
A04 -> Video QC
```

A03 即使 render 20 分钟，Supervisor 也不应阻塞等待。

它只需要知道：

```text
A03
state=running
step=render
heartbeat=healthy
```

然后继续处理其他工作。

---

## 8. OpenWorker 是状态 Authority

Supervisor 查询状态时，应由 OpenWorker 聚合：

```text
job_id
machine
agent_slot
dispatch_state
worker_state
task_state
current_step
heartbeat
pid
resource_locks
artifact_state
qc_state
error
```

GitHub Action 只保留 transport / CI / evidence 角色。

真正成功必须来自：

```text
job state
+
artifact receipt
+
必要的 QC receipt
```

---

## 9. Local Supervisor Identity

未来建议新增 Local Supervisor 一等身份：

```text
supervisor_id
machine
session_id
model
started_at
heartbeat_at
last_decision_at
current_goal
state
```

例如：

```text
supervisor_id = ODA-CODER-01
machine = DESKTOP-ODAQN0D
model = qwen-coder
state = active
```

Supervisor identity 与 worker slot identity 分离。

---

## 10. Supervisor Session 与 Snapshot

LLM 每次启动或 context reset 都建立新的 session_id。

```text
supervisor_id
= durable identity

session_id
= transient reasoning session
```

OpenWorker 应提供最小 durable Supervisor Snapshot：

```text
supervisor_id
machine
current_goal
owned_jobs
watched_jobs
blocked_jobs
failed_jobs
recent_completed_jobs
last_decision
next_attention
updated_at
```

Snapshot 不保存完整 chain-of-thought，只保存恢复工作所需的最小事实。

核心原则：

> 模型可以重启，工作不能失忆。

---

## 11. Supervisor 重启恢复

Local Coder 启动后应先：

```text
identify supervisor
        |
        v
load supervisor snapshot
        |
        v
query current OpenWorker jobs
        |
        v
query recent job events
        |
        v
compare durable state
        |
        v
recover working context
        |
        v
continue supervision
```

例如 crash 前：

```text
A01 running
A02 completed
A03 rendering
A04 failed
```

重启后直接从 OpenWorker 恢复，不依赖旧 LLM context。

---

## 12. 建议 Supervisor API

建议后续增加：

```text
GET  /v1/supervisor/snapshot
POST /v1/supervisor/session
POST /v1/supervisor/heartbeat
POST /v1/supervisor/decision
GET  /v1/supervisor/jobs
POST /v1/supervisor/recover
```

go-tool 暴露：

```text
openworker.supervisor.snapshot
openworker.supervisor.jobs
openworker.supervisor.recover
```

具体执行仍复用既有：

```text
openworker.job.submit
openworker.job.status
openworker.job.cancel
openworker.job.retry
openworker.queue.drain
openworker.cluster.status
openworker.cluster.jobs
openworker.cluster.agents
```

不要为 Supervisor 再复制一套 scheduler API。

---

## 13. Decision Receipt

Supervisor 的重要决策建议形成 durable receipt：

```text
decision_id
supervisor_id
session_id
machine
job_id
decision_type
reason_code
input_state_hash
created_at
```

decision_type：

```text
submit
retry
cancel
wait
inspect
replan
escalate
```

不保存完整 chain-of-thought，只保存可审计的 decision / reason_code / inputs / result。

---

## 14. Supervisor 与 Knowledge Graph

失败流程：

```text
job failed
   |
   v
read failure receipt
   |
   v
query Knowledge Graph
   |
   +--> known successful path
   |
   +--> known negative path
   |
   v
select next action
```

工具负面知识应直接提供给 Supervisor，避免重复已知错误。

---

## 15. Local Authority Boundary

每个 Local Supervisor 默认只管理本机：

```text
UL7-CODER -> UL7
ODA-CODER -> ODA
O87-CODER -> O87
```

可以观察整个 cluster，但默认 local-first。

只有明确允许跨节点调度的工作才使用：

```text
machine=any
required_capabilities=...
```

fixed-machine 工作仍遵守：

```text
COMPUTERNAME = final authority
```

不得因 Supervisor 自行判断而漂移。

---

## 16. 禁止多个 Local Supervisor 无边界互相抢工作

禁止：

```text
UL7 Coder 派 ODA
ODA Coder 又重派 UL7
O87 Coder 同时 retry
```

Local Supervisor 必须 local authority first。

跨机操作统一经 OpenWorker Cluster durable control，不做 supervisor-to-supervisor 直接遥控。

---

## 17. Progress Observation

只有：

```text
running
```

不够让 Supervisor 管理一台电脑。

OpenWorker 应逐步标准化：

```text
current_step
progress
message
heartbeat
artifact_state
qc_state
```

工具可回报：

```text
load_input
parse
build_model
render
export
qc
publish
```

例如：

```text
job_id = OWJ-...
state = running
current_step = render
progress = 72
message = Rendering frame 144/200
```

这样 Supervisor 才能判断正常执行还是疑似卡住。

---

## 18. Supervisor 不应过度轮询

未来建议提供：

```text
heartbeat
event ledger
changed_since
attention_required
```

以及可选：

```text
GET /v1/supervisor/attention
```

只返回真正需要模型处理的事件：

```text
job failed
job blocked
job stale
artifact ready
QC failed
human decision required
```

减少无意义 polling 与 token 消耗。

---

## 19. 第一阶段最小实现

不需要一次建立完整 Autonomous Supervisor Framework。

第一阶段只补：

```text
Supervisor identity
Supervisor session
Supervisor snapshot
Supervisor heartbeat
Supervisor recover
Decision receipt
```

并直接复用现有 OpenWorker：

```text
jobs
agents
events
cluster
capabilities
resource locks
retry
cancel
drain
```

---

## 20. 第一阶段验收

先选一台机器，例如 ODA：

```text
llama.cpp
+
Coder Supervisor
+
OpenWorkerNode
```

让 Coder 管理：

```text
A01 -> coding job
A02 -> test job
A03 -> ComfyX job
A04 -> QC job
```

验收至少包括：

1. Coder 能看到四个 slot；
2. 能 submit 多个工作；
3. 不等待长 job；
4. 能看到 current progress；
5. failed job 有 failure receipt；
6. 能查询负面知识；
7. 能决定 retry / replan；
8. 强制关闭 Coder；
9. OpenWorker jobs 继续执行；
10. 重启 Coder；
11. recover supervisor snapshot；
12. 找回 running / completed / failed jobs；
13. 不重复 submit；
14. artifact / QC receipt 正确。

只有完成后才能宣称：

```text
LOCAL CODER SUPERVISOR REAL VERIFIED
```

---

## 21. 与当前 P2 Cluster 架构的关系

P2 Cluster 解决：

```text
三台机器怎么执行
三台机器怎么互相看到
怎么 route
怎么 durable control
怎么 failover
```

Supervisor 解决：

```text
谁持续观察状态
谁判断下一步
谁处理失败
谁安排多个 jobs
谁在模型重启后恢复管理
```

两者是上下层关系，不是竞争关系。

---

## 22. 最终架构

```text
                 Human
                   |
                   v
                ChatGPT
          Global Supervisor / QC
                   |
                   v
          OpenWorker Control Plane
                   |
          OpenWorker Cluster State
          /         |          \
         /          |           \
        v           v            v
 UL7 Supervisor  ODA Supervisor  O87 Supervisor
   Local Coder     Local Coder      Local Coder
        |             |               |
        v             v               v
 OpenWorkerNode  OpenWorkerNode  OpenWorkerNode
        |             |               |
   A01-A04        A01-A04          A01-A04
```

其中：

```text
Human
= 最终业务决策

ChatGPT
= Global Supervisor / 成果质量控制 / 跨案例跨节点主控

Local Coder
= 每台电脑的 Local Supervisor

OpenWorker Python
= Control Plane

OpenWorker Go
= Durable Execution Kernel

Knowledge Graph
= 经验与失败知识

go-tool
= Agent 可操作能力面

GitHub Actions
= Transport / CI / Evidence
```

---

## 23. 最终原则

> ChatGPT 现在即可作为 Global Supervisor，不需要等待 Local Coder。

> Local Coder 是后续增加的本机高频 Supervisor，不是替代 ChatGPT。

> 模型可以重启，工作不能失忆。

> Agent 可以失败，整台机器不能一起卡死。

> Supervisor 负责决策，OpenWorker 负责事实。

> LLM context 不是数据库。

> GitHub Action 不是长任务 scheduler。

> Job progress 必须可查，不靠猜测。

> 已知失败必须形成负面知识，避免重复。

> 本机优先，跨机由 Cluster 明确协调。

> fixed machine 永不因 Agent 自作主张而漂移。

> 真正成功必须由 durable state、artifact 与必要 QC receipt 证明。

最终目标：

**ChatGPT 作为全局主控，未来每台 Windows 电脑再配置一个本机 llama.cpp Coder 作为 Local Supervisor；OpenWorker 则成为所有 Supervisor 底下可靠、可并行、可恢复、可观察的执行作业系统。**
