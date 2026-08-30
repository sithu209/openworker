# OpenWorker 本机 Coder Supervisor 第一阶段实现进度

日期：2026-08-18 13:01 +08:00  
上位设计：`2026-08-18-1252-OpenWorker本机Coder-Supervisor-Agent架构设计.md`  
状态：PHASE-1 IMPLEMENTED — WAITING FOR ODA LOCAL CODER REAL VERIFICATION

## 1. 本批结论

12:52 架构文档定义的第一阶段最小缺口已经落到 OpenWorker Go durable authority：

```text
Supervisor identity
Supervisor session
Supervisor snapshot
Supervisor heartbeat
Supervisor recover
Decision receipt
```

同时补了两个会直接影响 Supervisor 可用性的观察缺口：

```text
job progress
attention-only observation
```

因此 Local Coder 不需要自己记 PID、job 状态、上次做到哪里，也不需要只看到 `running` 后高频轮询。

当前仍未取得 ODA 本机 llama.cpp Coder 的真实启动/关闭/重启/recover receipt，所以不能宣称 `LOCAL CODER SUPERVISOR REAL VERIFIED`。

## 2. Durable Supervisor Identity / Session

提交 `ed7ea515` 新增：

```text
go-runtime/internal/store/supervisor.go
```

新增 SQLite authority：

```text
supervisors
supervisor_sessions
supervisor_snapshots
supervisor_decisions
```

Supervisor identity 与 LLM session 明确分离：

```text
supervisor_id
= durable identity

session_id
= transient model/reasoning session
```

例如：

```text
supervisor_id = ODA-CODER-01
session_id    = <每次模型启动的新 session>
machine       = DESKTOP-ODAQN0D
model         = qwen-coder
```

模型/context 可以重启；OpenWorker durable state 不跟着消失。

## 3. Supervisor Snapshot

Snapshot authority 保存最小恢复事实：

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

不保存完整 chain-of-thought。

`POST /v1/supervisor/recover` 会重新读取当前 OpenWorker durable jobs，而不是相信旧 snapshot：

```text
load durable supervisor
-> verify current session
-> query current jobs
-> classify failed/timed_out/stale
-> collect recent completed
-> merge explicit progress attention
-> load latest decision receipt
-> rebuild snapshot
-> persist snapshot
-> return recovered context
```

因此旧 snapshot 只是恢复线索；当前 job state 仍是最终 authority。

## 4. Decision Receipt

Decision receipt 字段：

```text
decision_id
supervisor_id
session_id
machine
job_id
decision_type
reason_code
input_state_hash
result
created_at
```

允许：

```text
submit
retry
cancel
wait
inspect
replan
escalate
```

未知 decision_type fail-closed。

明确禁止把模型隐藏推理过程写进 receipt；只保存可审计 decision、reason code、输入状态 hash 与结果摘要。

提交 `c4316263` 增加 durable session/snapshot/decision tests。

## 5. Supervisor API

提交：

- `8417dae7`：Supervisor API 主体；
- `4c1cfa86`：注册到 OpenWorkerNode HTTP server；
- `1b206c2d`：progress / attention 扩展。

当前 API：

```text
POST /v1/supervisor/session
POST /v1/supervisor/heartbeat
GET  /v1/supervisor/snapshot?supervisor_id=...
GET  /v1/supervisor/jobs?supervisor_id=...
POST /v1/supervisor/recover
POST /v1/supervisor/decision
GET  /v1/supervisor/decisions?supervisor_id=...
GET  /v1/supervisor/attention?supervisor_id=...
```

Supervisor API 不复制 submit/cancel/retry/drain scheduler；实际工作继续复用既有 OpenWorker job / cluster APIs。

## 6. Job Progress Durable Contract

提交 `6e804ea4` 新增：

```text
job_progress
```

字段：

```text
job_id
current_step
progress             0..100
message
artifact_state
qc_state
error
attention_required
updated_at
```

API：

```text
GET  /v1/jobs/{job_id}/progress
POST /v1/jobs/{job_id}/progress
```

工具以后可以标准回报：

```text
current_step = render
progress = 72
message = Rendering frame 144/200
artifact_state = pending
qc_state = waiting
```

这样 Supervisor 不再只能看到 `running`。

`5b73e782` 增加 progress/attention durable test。

## 7. Attention-only Observation

`GET /v1/supervisor/attention` 只返回真正需要模型关注的项目：

```text
job_failed
job_timed_out
job_stale
progress_attention
```

同时 `recover` 会把这些 job_id 合并到：

```text
next_attention
```

这为后续低频 Supervisor loop 提供基础，避免 Local Coder 每几秒把所有 jobs 全扫一次。

注意：artifact ready / QC failed / human decision required 目前需要业务工具通过 `job_progress.attention_required + artifact_state/qc_state/message` 上报；后续可再标准化 reason code，但 durable transport 已具备。

## 8. Python Control Plane

提交：

- `cb6e7f8c`：Supervisor session/snapshot/recover/decision client；
- `ee90f1ee`：job progress + supervisor attention client。

`OpenWorkerNodeClient` 现在提供：

```text
supervisor_session
supervisor_heartbeat
supervisor_snapshot
supervisor_jobs
supervisor_attention
supervisor_recover
supervisor_decision
supervisor_decisions
job_progress
update_job_progress
```

Python 上层不需要手写 HTTP。

## 9. go-tool Supervisor Capability

OpenWorker：

- `4acaa922`：统一 `scripts/openworker_supervisor_control.ps1`；
- `276e20e2`：ODA Supervisor Action transport；
- `f7959c14`：加入 attention operation。

go-tool-runtime：

- `09f1a725`：注册 `openworker.supervisor.control`；
- `7718a661`：加入 attention 与 progress authority 负面知识。

支持：

```text
session
heartbeat
snapshot
jobs
attention
recover
decision
decisions
```

工具说明明确：

```text
LLM context != Supervisor durable state
Action completed != business job succeeded
Supervisor API != another scheduler
Decision receipt != chain-of-thought log
```

## 10. API Contract Tests

提交 `f71fa230` 增加 API tests：

```text
session create
heartbeat
recover from durable jobs
decision receipt
old session decision reject
```

重点验证：旧 LLM session 不能在新 session 接管后继续写 decision。

## 11. ODA Phase-1 Verification Entry

提交 `a84678e0` 新增：

```text
.github/workflows/openworker-supervisor-phase1-verify.yml
```

固定：

```text
runner: ODA
COMPUTERNAME: DESKTOP-ODAQN0D
```

执行：

```text
go test ./internal/store ./internal/api
go test ./...
go build ./cmd/openworker-node
PowerShell supervisor transport parse check
```

只要 Action 能接单并进入执行，可证明 transport/routing 可用；但不能据此宣称 Local Coder Supervisor 的真实业务验收完成。

## 12. 当前相对 12:52 文档的缺口状态

第一阶段最小实现：

```text
Supervisor identity     DONE
Supervisor session      DONE
Supervisor snapshot     DONE
Supervisor heartbeat    DONE
Supervisor recover      DONE
Decision receipt        DONE
```

观察增强：

```text
current_step            DONE via job_progress
progress                DONE
message                 DONE
artifact_state          DONE transport
qc_state                DONE transport
attention_required      DONE
attention endpoint      DONE
```

仍需 REAL 验证：

```text
ODA llama.cpp Coder 真正作为 Local Supervisor 启动
Coder 创建 session
Coder 同时管理 A01-A04
长 job 时 Supervisor 不阻塞
业务工具真实写 progress
强制关闭 Coder
OpenWorker jobs 继续运行
重启 Coder / 新 session
recover snapshot
找回 running/completed/failed jobs
不重复 submit
读取 failure/negative knowledge
artifact/QC receipt 闭环
```

## 13. 下一步不再继续扩 scheduler

下一步应该直接做 ODA REAL Supervisor smoke，而不是继续造一套新的调度系统：

```text
ODA Local Coder
-> openworker.supervisor.control session
-> observe jobs/agents/attention
-> submit 4 个实际工作
-> durable ACK 后继续观察而不是等待
-> 模拟 Coder crash
-> jobs 继续
-> new session
-> recover
-> 决策 retry/replan
```

真实 smoke 通过后，再复制 Local Supervisor identity 到：

```text
UL7-CODER-01
O87-CODER-01
```

## 14. 状态声明

截至本文件：

**Supervisor Phase-1 code contract 已 IMPLEMENTED。**

**尚未取得 ODA Local Coder 的真实 crash/recover/4-slot/artifact-QC 验收证据，因此不是 LOCAL CODER SUPERVISOR REAL VERIFIED。**
