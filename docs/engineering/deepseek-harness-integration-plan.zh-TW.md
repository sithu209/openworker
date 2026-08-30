# OpenWorker × DeepSeek Harness 詳細整合設計

> 狀態：**DESIGN / IMPLEMENTATION PLAN — 尚未開始 Runtime 整合程式碼**  
> 日期：2026-08-14  
> OpenWorker 目標分支：`engineering-e6-4-public-api-e2e`  
> 研究前置文件：`docs/engineering/deepseek-harness-integration-research.zh-TW.md`  
> DeepSeek Harness：`deepseek-ai/deepseek-harness`（Developer Preview）

---

## 0. 文件目的

本文件把前一份「架構研究」轉成可以直接照著開發的整合規格。

核心目標不是把 DeepSeek Harness 當成一個新的模型 Provider，而是讓 OpenWorker 具備可替換的 Agent Runtime：

```text
OpenWorker
    │
    ├── NativeRuntime
    │      └── 現有 TurnEngine
    │
    └── DeepSeekHarnessRuntime
           └── OpenWorker 管理的 dsh sidecar + plugins/profile
```

整合後必須同時做到：

1. OpenWorker 現有功能不能因為加入 Harness 而倒退。
2. 現有 `TurnEngine` 暫時保留，可隨時 fallback。
3. DeepSeek Harness 的 Agent Loop / Session / Tool Pipeline / Jobs 等真正能力可以被使用，而不是只拿來做單次 LLM 呼叫。
4. OpenWorker Permission / Approval 仍是 user-facing 安全權威。
5. AI-Engineering-OS 仍是工程 Tool / Recipe / Job / Artifact / Review / Delivery 的唯一工程權威。
6. Harness upstream 盡量不直接魔改；先以 profile / plugin / bridge 擴充。
7. 若 upstream extension point 不足，才逐級進入 patch，最後才 fork core。
8. 必須用真實 Golden Job A/B 驗證，不能只靠聊天 smoke test 宣稱整合成功。

---

# 1. 最終要得到的系統

```text
┌─────────────────────────────────────────────────────────────┐
│ User / Desktop / Web / Telegram / Connector                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ OpenWorker Product Layer                                    │
│                                                             │
│ UI / Workspace / Connector / Memory / Automation           │
│ Permission / Approval / Notification / Finished Work UX    │
│                                                             │
│                 AgentRuntimeManager                         │
│                 ├─ NativeRuntime                            │
│                 └─ DeepSeekHarnessRuntime                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
              HarnessRuntime selected
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ DeepSeek Harness sidecar                                    │
│                                                             │
│ Agent Loop / Session Event Log / Tool Orchestration        │
│ Jobs / Context / Planning / Subagent / Plugin Runtime      │
│                                                             │
│ OpenWorker profile                                          │
│ ├─ openworker-bridge plugin                                 │
│ ├─ tool-gateway plugin                                      │
│ ├─ approval-bridge plugin                                   │
│ ├─ session-bridge plugin                                    │
│ ├─ jobs-bridge plugin                                       │
│ └─ engineering-os plugin                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ Tool request
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ OpenWorker Tool / Permission Gateway                        │
│                                                             │
│ PermissionEngine → user approval → execute → normalize     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ AI-Engineering-OS                                          │
│                                                             │
│ Canonical Tool Contract / Recipe / Engineering Job         │
│ Artifact / Review / Delivery / Digital Thread              │
└─────────────┬───────────────────┬───────────────────────────┘
              │                   │
              ▼                   ▼
           ComfyX          Design Forge / DWG / BIM / Terrain
```

使用者感受到的是「同一個 OpenWorker」，不是另外開一套 Harness UI。

---

# 2. Repository 目錄設計

## 2.1 第一版建議目錄

在 OpenWorker repository 建立一個明確的 `harness/` integration root：

```text
openworker/
│
├── coworker/
│   ├── engine.py                         # 現有 TurnEngine，不直接刪除
│   ├── permissions.py                    # 現有 PermissionEngine
│   ├── tools/
│   │   └── registry.py
│   │
│   └── runtimes/                         # 新增：OpenWorker runtime abstraction
│       ├── __init__.py
│       ├── base.py                       # AgentRuntime protocol / ABC
│       ├── manager.py                    # Runtime selection/lifecycle
│       ├── events.py                     # normalized runtime event contract
│       ├── native.py                     # TurnEngine adapter
│       └── harness.py                    # Python ↔ dsh adapter
│
├── harness/                              # 新增：Harness integration root
│   ├── README.zh-TW.md
│   ├── package.json
│   ├── pnpm-lock.yaml                    # 鎖定完整依賴樹
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.ts                       # sidecar entry
│   │   ├── protocol.ts                   # IPC message schema
│   │   ├── runtime-server.ts             # local control endpoint / IPC server
│   │   └── health.ts
│   │
│   ├── profiles/
│   │   └── openworker/
│   │       ├── index.ts                  # OpenWorker Harness profile
│   │       └── config.ts
│   │
│   ├── plugins/
│   │   ├── openworker-bridge/
│   │   │   └── index.ts
│   │   ├── tool-gateway/
│   │   │   └── index.ts
│   │   ├── approval-bridge/
│   │   │   └── index.ts
│   │   ├── session-bridge/
│   │   │   └── index.ts
│   │   ├── jobs-bridge/
│   │   │   └── index.ts
│   │   └── engineering-os/
│   │       └── index.ts
│   │
│   ├── patches/                          # 只有確有必要才放 patch
│   │   ├── README.md
│   │   └── series.json
│   │
│   ├── upstream/                         # 第一階段預設不存在
│   │   └── README.md                     # 只有正式 fork/vendor 才啟用
│   │
│   └── tests/
│       ├── protocol.test.ts
│       ├── tool-gateway.test.ts
│       ├── approval-bridge.test.ts
│       └── session-bridge.test.ts
│
├── surfaces/
│   └── gui/
│       └── src-tauri/
│           └── ...                       # 後期管理第二個 sidecar
│
├── tests/
│   ├── runtimes/
│   │   ├── test_native_runtime.py
│   │   ├── test_harness_runtime.py
│   │   ├── test_runtime_parity.py
│   │   └── test_runtime_fallback.py
│   └── engineering/
│       └── ... existing Golden Job tests
│
└── docs/engineering/
    ├── deepseek-harness-integration-research.zh-TW.md
    └── deepseek-harness-integration-plan.zh-TW.md
```

## 2.2 `harness/` 的定位

`harness/` **不是第一天就把 `deepseek-ai/deepseek-harness` 整個 repository 複製進來。**

第一階段它代表：

```text
OpenWorker-specific Harness integration package
```

裡面主要放：

- OpenWorker profile；
- OpenWorker plugins；
- sidecar entry；
- IPC protocol；
- build/package 設定；
- integration tests；
- 少量必要 patch。

Harness 官方 package / commit 必須被精確 pin 住。

## 2.3 什麼時候才建立 `harness/upstream/`

只有出現以下情況才考慮：

1. 官方 plugin extension point 無法攔截必要 lifecycle；
2. session / tool / job API 缺少我們必須的 hook；
3. 無法實作 interrupt/resume/approval bridge；
4. upstream bug 長期阻塞實際 Golden Job；
5. 官方沒有接受我們需要的修正；
6. patch 數量已經多到 package patch 難以管理。

屆時才把 Harness fork/vendor 成：

```text
harness/upstream/
```

但仍要保持：

```text
upstream core
      ↑
patch / fork delta
      ↑
OpenWorker plugins/profile
```

不能讓 OpenWorker-specific business logic 散落到 upstream core。

---

# 3. 魔改策略：四級制

整合時所有需求按照下面順序處理。

## Level 0 — 官方能力直接使用

例如官方已提供：

- agent loop；
- session；
- tool registry；
- jobs；
- model adapters；
- plugin lifecycle。

直接組 profile，不改 core。

## Level 1 — OpenWorker plugin

優先透過 Harness plugin 加入：

- OpenWorker event bridge；
- OpenWorker tool gateway；
- OpenWorker approval；
- OS tool discovery；
- telemetry mapping。

這是預期的大部分整合工作。

## Level 2 — Patch upstream package

只有 upstream 小缺口時，使用可追蹤 patch。

每一個 patch 都必須記錄：

```text
patch id
upstream commit/version
reason
modified files
upstream issue/PR if any
tests covering the patch
removal condition
```

## Level 3 — Fork Harness Core

只有 plugin + patch 都不能合理解決時才 fork。

Fork 後也必須：

- 固定 upstream base commit；
- 維護 `UPSTREAM.md`；
- 維護 patch/delta 清單；
- 每次升級跑完整 A/B Golden Job；
- 禁止無紀錄直接改 core。

---

# 4. AgentRuntime 抽象層

## 4.1 為什麼一定要先做 Runtime seam

現在 `TurnEngine` 同時負責完整 agent loop。

不能直接：

```text
TurnEngine = Harness
```

否則所有 UI/server/session call site 都會跟著被改，回退非常困難。

應先變成：

```text
OpenWorker surfaces
       │
       ▼
AgentRuntimeManager
       │
       ├── NativeRuntime(TurnEngine)
       └── DeepSeekHarnessRuntime
```

第一個 Runtime PR 必須是**零行為變更**：預設仍走 NativeRuntime。

## 4.2 建議 Runtime contract

以下是設計 contract，實作前仍應依目前 OpenWorker manager/server call site 校正命名：

```python
class AgentRuntime(Protocol):
    async def health(self) -> RuntimeHealth: ...

    async def create_session(
        self,
        *,
        openworker_session_id: str,
        runtime_config: RuntimeConfig,
    ) -> RuntimeSession: ...

    async def submit_turn(
        self,
        *,
        session_id: str,
        user_input: UserTurnInput,
    ) -> AsyncIterator[RuntimeEvent]: ...

    async def interrupt(
        self,
        *,
        session_id: str,
        turn_id: str | None = None,
    ) -> None: ...

    async def resume(
        self,
        *,
        session_id: str,
    ) -> AsyncIterator[RuntimeEvent]: ...

    async def shutdown_session(self, *, session_id: str) -> None: ...

    async def shutdown(self) -> None: ...
```

不能把 Provider-specific request/response type 暴露到這層。

## 4.3 Runtime selection

初期建議：

```text
runtime = native   # default
runtime = harness  # opt-in experimental
```

配置優先級可設計為：

```text
per-session override
    > workspace setting
    > app setting
    > default(native)
```

在 Harness 通過 Golden Job 前，禁止把預設值改為 Harness。

---

# 5. Python ↔ Node/TypeScript 整合方式

DeepSeek Harness 本身是 Node/TypeScript/Cordis 生態，因此不應重寫成 Python。

## 5.1 第一版採 sidecar

```text
Tauri
  │
  ├── openworker-server     Python
  │
  └── openworker-harness    Node/TS
```

或第一個原型：

```text
openworker-server
      │ child process
      └── openworker-harness
```

最終由誰管理 sidecar，要等實際 Tauri lifecycle 與 server lifecycle 測試後決定。

## 5.2 IPC 原則

不要讓 Python import Node，也不要讓 Node import Python。

兩者透過明確 protocol 溝通：

```text
command request
runtime events
approval request/response
tool request/result
interrupt
health
shutdown
```

正式實作前先確認官方 dsh 是否已提供穩定 headless control API；若沒有，就由我們自己的 Harness plugin/profile 暴露最薄的 localhost/stdio IPC。

**不能為了方便而依賴 Harness Web UI 的內部未保證 endpoint。**

## 5.3 Protocol 必須 versioned

例如：

```json
{
  "protocol_version": 1,
  "type": "turn.submit",
  "request_id": "...",
  "session_id": "...",
  "payload": {}
}
```

每個 message 至少要有：

- `protocol_version`
- `type`
- `request_id`
- `session_id`（適用時）
- `turn_id`（適用時）
- `payload`
- `timestamp`

## 5.4 Local security

即使只綁 localhost，也要：

- random per-launch auth token；
- localhost only；
- 不暴露 LAN；
- health endpoint 不輸出 credentials；
- tool payload log 做 secret redaction；
- sidecar inherited env 最小化；
- shutdown 時清理 temporary token。

---

# 6. Runtime Event 統一

OpenWorker UI 不應知道底下是 TurnEngine 還是 dsh。

因此需要 normalized event contract。

## 6.1 建議事件類型

```text
runtime.session.started
runtime.session.ready

turn.started
turn.steering
turn.completed
turn.failed
turn.interrupted

assistant.reasoning.delta
assistant.text.delta
assistant.message.completed

tool.requested
tool.permission.required
tool.approval.requested
tool.started
tool.progress
tool.completed
tool.failed

job.started
job.progress
job.completed
job.failed
job.cancelled

artifact.created
warning
error
```

## 6.2 Harness → OpenWorker event mapping

Harness 原生事件不直接傳到 React/Tauri UI。

必須：

```text
Harness native event
       ↓
HarnessRuntime adapter
       ↓
Normalized RuntimeEvent
       ↓
OpenWorker websocket/event bus
       ↓
UI
```

這樣未來 Harness upstream 更改 event 名稱，只改 adapter。

## 6.3 NativeRuntime 也必須走相同 contract

這是 A/B 測試成立的必要條件。

不能：

```text
Native → 舊 UI event
Harness → 新 UI event
```

否則兩個 runtime 的行為無法公平比較。

---

# 7. Tool 整合方式

這是整合最重要的部分之一。

## 7.1 Harness 可以選 Tool，但不能直接繞過 OpenWorker 執行

正式路徑：

```text
Harness agent loop
      │
      │ chooses tool
      ▼
Harness tool-gateway plugin
      │
      ▼
OpenWorker Tool Gateway
      │
      ├─ resolve tool
      ├─ validate arguments
      ├─ PermissionEngine
      ├─ optional user approval
      ├─ execute
      ├─ normalize result
      └─ audit/event
      │
      ▼
Harness tool/result
```

## 7.2 OpenWorker-owned tools

現有 ToolRegistry 可透過 gateway 暴露給 Harness。

Harness model-facing schema 可以由 OpenWorker registry 產生，但 tool execute 最終必須回 OpenWorker。

禁止在 TypeScript 再複製一份 Python tool business logic。

## 7.3 AI-Engineering-OS tools

工程 tool 不應手工複製到 Harness。

優先動態發現：

```http
GET /api/v1/ai/tools
GET /api/v1/ai/tools/openai
GET /api/v1/ai/capabilities
GET /api/v1/ai/recipes
```

執行：

```http
POST /api/v1/ai/tools/{tool_id}/invoke
POST /api/v1/ai/execute
```

工程 tool schema 的 source of truth 始終是 OS。

## 7.4 ToolResult 必須保留工程證據

Harness adapter 不能只把結果壓成：

```json
{"text": "success"}
```

至少要保留 OS 的：

```text
status
tool
run_id
summary
result
artifacts
trace
warnings
assumptions
evidence
next_possible_tools
retryable
recovery_actions
error
```

否則會破壞 Agent recovery 與 Digital Thread。

---

# 8. Permission / Approval 整合

## 8.1 權威劃分

```text
Harness internal sandbox policy
        = runtime internal safety

OpenWorker PermissionEngine
        = user-facing product authority

AI-Engineering-OS approval/review
        = engineering governance authority
```

三者不能互相取代。

## 8.2 Approval state machine

```text
Harness requests consequential tool
          │
          ▼
OpenWorker PermissionEngine
          │
    ┌─────┴─────────┐
    │               │
  ALLOW           ASK_USER
    │               │
    │               ▼
    │        UI approval request
    │               │
    │        ┌──────┴──────┐
    │        │             │
    │      approve        deny
    │        │             │
    ▼        ▼             ▼
 execute tool           denied result
    │                       │
    └────────────┬──────────┘
                 ▼
          Harness tool/result
```

## 8.3 禁止 double approval

如果 OpenWorker 已經對同一 operation 做 user approval，Harness plugin 不應再顯示第二套人機 approval UI。

需要在 protocol 中保留：

```text
approval_id
permission_decision
approval_scope
approved_by
approved_at
```

## 8.4 Auto mode 仍受邊界限制

OpenWorker `AUTO` 不是「無限制」。

Harness 必須尊重：

- workspace path scope；
- connector target scope；
- shell constraints；
- task standing rules；
- publish/delivery governance。

---

# 9. Session / Memory 整合

這是另一個高風險區。

## 9.1 不允許兩套 model-visible history 同時當主資料

Harness 原則：

```text
Model-visible means logged.
```

因此 HarnessRuntime active 時，runtime/model-visible turn log 應由 Harness session log 負責。

OpenWorker 保留：

- product session id；
- UI transcript projection；
- workspace metadata；
- stable user memory；
- automation metadata；
- runtime selection；
- artifact references。

## 9.2 ID mapping

至少需要：

```text
OpenWorkerSessionId ↔ HarnessSessionId
OpenWorkerTurnId    ↔ HarnessTurnId
OpenWorkerToolCallId↔ HarnessToolCallId
OpenWorkerJobId     ↔ HarnessRuntimeJobId (if applicable)
```

mapping 必須可持久化，不能只存在 RAM。

## 9.3 Memory 注入

OpenWorker 的長期 memory 不直接寫進 Harness session store 當另一個 truth source。

建議：

```text
OpenWorker memory retrieval
       ↓
runtime context adapter
       ↓
Harness system/context assembly
```

必要時記錄「本 turn 使用了哪些 memory references」，但原始穩定 memory 仍由 OpenWorker 管。

## 9.4 Transcript

UI transcript 應從 normalized events / persisted projection 重建。

不要讓 UI 一半讀 OpenWorker message DB、一半讀 Harness session DB。

---

# 10. Job 與長任務整合

必須明確區分三種 Job。

## 10.1 Runtime Job

Owner：Harness/OpenWorker runtime。

例如：

- subagent；
- background reasoning task；
- agent runtime internal job。

## 10.2 Product Automation Job

Owner：OpenWorker Automation/Scheduler。

例如：

- 每天 08:00 做工作摘要；
- 定期檢查某資料；
- 使用者建立的 recurring coworker task。

## 10.3 Engineering Job

Owner：AI-Engineering-OS。

例如：

- RC design job；
- terrain job；
- DWG flow；
- BIM generation；
- ComfyX video generation as OS-routed specialist work。

## 10.4 ID 不可混用

例如：

```text
runtime_job_id     = hrj_...
automation_task_id = oat_...
engineering_job_id = eos_...
```

UI 可以把三者呈現在同一個工作畫面，但 backend lifecycle authority 不同。

## 10.5 Cancellation

```text
User clicks Stop
      │
      ▼
OpenWorker runtime manager
      │
      ├─ stop Harness active turn/runtime job
      │
      └─ if active tool owns cancellable OS job
                ↓
           OS cancel endpoint
```

不能只停止模型 streaming 卻讓工程 job 在背後繼續燒 GPU。

同樣也不能把「停止 agent」一律解讀成「刪除所有 OS job」。要依 tool/job contract 判定。

---

# 11. AI-Engineering-OS 邊界

Harness integration 後，下面原則不能改：

```text
AI-Engineering-OS = Engineering Control Plane
```

Harness 不得：

- 自己定義另一套 RC workflow；
- 自己複製 OS recipe；
- 自己決定工程 publish approval；
- 自己建立另一套 engineering artifact authority；
- 直接繞過 OS 呼叫 specialist engine 當正式 Golden Path。

正式工程路徑仍是：

```text
Harness / OpenWorker
       ↓
AI-Engineering-OS
       ↓
Canonical tool / recipe
       ↓
Specialist engine
```

低階 debugging 可以直接打 specialist engine，但不能變成正式產品 workflow。

---

# 12. ComfyX 等 specialist engine 的角色

以 ComfyX 為例：

```text
User: 做施工模擬影片
      ↓
OpenWorker + Harness
      ↓
AI-Engineering-OS tool/recipe
      ↓
ComfyX
      ↓
H3 / LightX2V / ComfyUI Desktop
      ↓
real MP4 artifact
```

Harness 不需要知道 MiniMax H3 的所有 ComfyUI node 細節。

它只需要看到工程/能力語意層 tool，例如：

```text
video.generate_construction_simulation
video.generate_reference_motion
```

底層到底走 H3、LightX2V、T8、ComfyUI Desktop，交給 OS + ComfyX adapter 管理。

---

# 13. Harness Profile 設計

建立：

```text
harness/profiles/openworker/
```

這個 profile 是 OpenWorker 對 Harness 的「組裝入口」。

建議內容：

```text
base harness capabilities
+ selected LLM adapter
+ openworker-bridge
+ tool-gateway
+ approval-bridge
+ session-bridge
+ jobs-bridge
+ engineering-os
+ telemetry hooks
```

不要讓各 plugin 在 entry point 裡隨意硬編碼互相依賴。

Profile 負責 composition，plugin 負責單一 capability。

---

# 14. 各 Plugin 職責

## 14.1 `openworker-bridge`

負責：

- runtime handshake；
- protocol version；
- OpenWorker session/turn context；
- normalized event output；
- health/capabilities；
- shutdown lifecycle。

不負責具體 tool business logic。

## 14.2 `tool-gateway`

負責：

- 接收 Harness tool calls；
- 轉成 OpenWorker gateway request；
- 等待 OpenWorker permission/execute；
- 將 result 回寫成 Harness tool result。

## 14.3 `approval-bridge`

負責：

- pending approval；
- approval IDs；
- suspend/resume tool execution；
- approve/deny result mapping。

不建立第二套 UI。

## 14.4 `session-bridge`

負責：

- OpenWorker session ID mapping；
- transcript projection events；
- resume metadata；
- session lifecycle notifications。

## 14.5 `jobs-bridge`

負責：

- runtime job event mapping；
- cancel/stop；
- background job collection；
- 與 engineering job reference 分離。

## 14.6 `engineering-os`

負責：

- OS capability discovery；
- tool schema exposure；
- canonical ToolResult preservation；
- engineering job/artifact references。

第一版如果 OpenWorker 已有成熟 OS facade，也可以讓此 plugin 只呼叫 OpenWorker tool gateway，而不直接打 OS。這樣更容易保留單一 permission path。

---

# 15. Dependency 與版本鎖定

Harness 官方目前是 Developer Preview，因此必須避免 floating dependency。

禁止：

```json
"@deepseek-ai/dsh": "latest"
```

必須：

- exact npm version；或
- exact Git commit；
- lockfile committed；
- runtime health 回報 Harness version/commit。

每次升級流程：

```text
pin new version
    ↓
compile
    ↓
plugin/unit tests
    ↓
protocol tests
    ↓
Native/Harness parity tests
    ↓
RC Golden Job
    ↓
ComfyX long-running Golden Job
    ↓
compare report
    ↓
accept/reject upgrade
```

---

# 16. Build / Packaging

## 16.1 Development

開發環境允許：

```text
Python OpenWorker server
Node/pnpm Harness package
```

各自 build，但由一個 repo 管理。

## 16.2 Desktop production

最終要產出：

```text
openworker-server
openworker-harness
```

Tauri package 要知道：

- binary/package path；
- start args；
- auth token；
- health probe；
- logs；
- stop/kill policy。

## 16.3 不能要求使用者手動先開 dsh

開發 smoke 可以人工啟動。

正式 OpenWorker Desktop 必須由應用自己管理 Harness runtime lifecycle。

---

# 17. Health / Capability Probe

HarnessRuntime 啟動後不能只檢查 process 存在。

health 至少包含：

```json
{
  "status": "ready",
  "protocol_version": 1,
  "harness_version": "...",
  "profile": "openworker",
  "capabilities": {
    "agent_loop": true,
    "tools": true,
    "session": true,
    "jobs": true,
    "interrupt": true,
    "resume": true
  }
}
```

OpenWorker 啟動 Harness session 前先 capability check。

若缺必要 capability：

```text
Harness unavailable
      ↓
mark runtime unhealthy
      ↓
fall back to NativeRuntime
```

是否自動 fallback 要讓使用者/設定知道，不能 silently 改 runtime 而完全不記錄。

---

# 18. Error / Recovery Contract

HarnessRuntime error 不能全部變成 HTTP 500。

至少區分：

```text
RUNTIME_UNAVAILABLE
RUNTIME_PROTOCOL_MISMATCH
RUNTIME_SESSION_NOT_FOUND
RUNTIME_TURN_FAILED
RUNTIME_INTERRUPTED
TOOL_PERMISSION_DENIED
TOOL_EXECUTION_FAILED
ENGINEERING_JOB_FAILED
ENGINEERING_JOB_TIMEOUT
MODEL_PROVIDER_FAILED
HARNESS_PLUGIN_FAILED
HARNESS_UPSTREAM_INCOMPATIBLE
```

每個 error 應有：

```text
code
message
retryable
runtime
session_id
turn_id
cause
recovery_actions
```

例如：

```text
HARNESS_UPSTREAM_INCOMPATIBLE
retryable=false
recovery_actions=["switch_to_native_runtime"]
```

---

# 19. Logging / Observability

每個 turn 都應能串起：

```text
OpenWorker session_id
OpenWorker turn_id
Harness session_id
Harness turn/step id
Tool call id
Engineering OS run_id/job_id
Artifact ids
```

但 log 禁止直接輸出：

- API keys；
- connector secrets；
- full auth token；
- sensitive file contents unless debug explicitly enabled。

必要 metrics：

```text
turn latency
model latency
tool latency
number of model calls
number of tool calls
duplicate tool calls
approval wait time
interrupt latency
resume success
runtime crash count
Harness restart count
engineering artifact completeness
token/cost if available
```

---

# 20. 開發階段與提交順序

以下順序是本整合的正式建議，不應直接跳到 Harness core 魔改。

## Phase H0 — Architecture Freeze

內容：

- 完成本文件；
- 確認現有 TurnEngine/server/session/WS/approval call sites；
- 深入讀 Harness headless、agent lifecycle、session、tools、jobs、plugin API；
- 確定 IPC/control seam。

完成條件：

- 沒有未決的 runtime ownership 問題；
- 有正式 event mapping；
- 有 session/job/approval mapping。

## Phase H1 — AgentRuntime seam（零行為變更）

新增：

```text
coworker/runtimes/base.py
coworker/runtimes/native.py
coworker/runtimes/manager.py
coworker/runtimes/events.py
```

把現有 TurnEngine 包成 NativeRuntime。

完成條件：

- 所有既有 tests 綠；
- OpenWorker 預設行為完全一致；
- UI 不知道 seam 已加入。

## Phase H2 — `harness/` skeleton + build

新增：

```text
harness/package.json
harness/src/
harness/profiles/openworker/
harness/plugins/
```

只做到：

- pinned Harness dependency；
- build；
- health；
- start/stop；
- protocol handshake。

不先接工程 tools。

完成條件：

- Python 可以啟動/停止 dsh sidecar；
- version/capability probe 可用；
- process crash 可被偵測。

## Phase H3 — HarnessRuntime basic turn

新增：

```text
coworker/runtimes/harness.py
```

完成最小：

```text
create session
submit text turn
stream normalized text/reasoning events
interrupt
turn complete/fail
```

完成條件：

- UI 可選 experimental Harness runtime；
- 純聊天可用；
- interrupt 真實有效；
- Native fallback 可用。

## Phase H4 — Tool Gateway + Permission Bridge

接上 OpenWorker tools。

完成條件：

- read tool；
- write tool approval；
- exec/shell approval；
- deny；
- Auto mode；
- path scope；
- external connector scope；
- 沒有 double approval；
- Harness 不可 bypass PermissionEngine。

## Phase H5 — Session / Resume

完成：

- ID mapping persistence；
- Harness session resume；
- UI transcript projection；
- orphan tool-call recovery；
- app/server restart recovery。

完成條件：

- 重啟後可 resume；
- 不產生雙份 model-visible history；
- UI transcript 不重複。

## Phase H6 — Engineering OS Dynamic Tools

接：

```text
/api/v1/ai/tools
/api/v1/ai/tools/openai
/api/v1/ai/execute
```

完成條件：

- Harness 不內建複製工程 schema；
- ToolResult evidence/artifacts/trace 完整保留；
- OS 仍是 workflow authority。

## Phase H7 — Jobs / Cancellation

完成：

- Harness runtime jobs；
- OpenWorker automation job distinction；
- OS engineering job references；
- stop/cancel propagation；
- long-running tool progress。

## Phase H8 — RC Column Golden Job A/B

同一 input：

```text
Runtime A = NativeRuntime
Runtime B = HarnessRuntime
```

比較：

- task success；
- tool correctness；
- calls；
- duplicates；
- approval correctness；
- calculation artifact；
- drawing artifact；
- BIM artifact；
- review state；
- no auto publish；
- evidence；
- elapsed time；
- token/cost；
- recovery。

## Phase H9 — ComfyX 長任務 Golden Job

驗證：

```text
OpenWorker/Harness
   → OS
   → ComfyX
   → real generation
   → non-empty readable MP4 artifact
```

必測：

- long timeout；
- job progress；
- cancel；
- resume；
- artifact retrieval；
- generation completed but empty artifact 應判失敗。

## Phase H10 — Desktop packaging

Tauri 管理 production Harness sidecar。

完成條件：

- 一鍵啟動；
- 無需人工 npm/pnpm；
- crash recovery；
- clean shutdown；
- logs；
- version diagnostics。

## Phase H11 — Promotion decision

只有 A/B 結果證明 Harness 明顯成熟，才考慮：

```text
default runtime = harness
```

否則維持 opt-in。

---

# 21. 測試矩陣

## 21.1 Runtime contract tests

Native 與 Harness 都跑同一套：

```text
create session
submit turn
stream
complete
interrupt
resume
failure
shutdown
```

## 21.2 Permission tests

```text
Discuss: write denied
Plan: write denied
Interactive: asks approval
Interactive deny: no execution
Interactive approve: executes once
Auto: allowed only inside scope
shell disallowed operators: rejected
external target: approval rules respected
```

## 21.3 Session tests

```text
restart server
restart sidecar
resume pending turn
recover pending tool result
avoid duplicate message
avoid duplicate tool execution
```

## 21.4 Harness crash tests

```text
kill sidecar mid-turn
kill sidecar during tool wait
protocol mismatch
plugin startup failure
model provider failure
```

每種情況都必須有可理解 recovery，而不是 OpenWorker 整個掛掉。

## 21.5 Engineering tests

至少：

```text
RC Column Golden Job
工程 tool discovery
ToolResult evidence preservation
artifact completeness
review state
no unintended publish
```

## 21.6 ComfyX tests

成功標準不是 API 200，也不是 workflow completed。

成功必須是：

```text
real generation
non-zero artifact
readable MP4
expected metadata
trace back to job/run
```

---

# 22. A/B 評分標準

對每個 Golden Job 建立 scorecard。

建議：

| 指標 | Native | Harness | 判斷 |
|---|---:|---:|---|
| 任務完成 | | | |
| 工具選擇正確率 | | | |
| 不必要 tool calls | | | |
| duplicate calls | | | |
| Approval 正確 | | | |
| Artifact 完整 | | | |
| Evidence 完整 | | | |
| Resume 成功 | | | |
| Cancel 成功 | | | |
| elapsed time | | | |
| model calls | | | |
| tokens | | | |
| cost | | | |
| runtime crashes | | | |

Harness 的 promotion 不是因為「官方新」或「看起來架構漂亮」，而是因為真實分數勝出。

---

# 23. 不可回退的架構規則

後續實作必須遵守：

1. **OpenWorker 是產品層。**
2. **Harness 是可替換 Agent Runtime，不是另一個產品入口。**
3. **AI-Engineering-OS 是工程控制面。**
4. **Specialist repo 是執行引擎，不擁有整體 Agent workflow。**
5. **TurnEngine 在 Harness 驗證前不可刪除。**
6. **Harness 不可只包成 ProviderClient 當正式方案。**
7. **Harness 不可繞過 OpenWorker PermissionEngine。**
8. **工程 workflow 不得複製進 Harness。**
9. **Session model-visible history 不得有兩個 source of truth。**
10. **Runtime Job / Automation Job / Engineering Job 不得混為同一 lifecycle。**
11. **Harness dependency 必須 pin exact version/commit。**
12. **先 plugin，再 patch，最後才 fork core。**
13. **每個 upstream core patch 都要有紀錄、測試與移除條件。**
14. **正式 Desktop 不要求使用者手動啟動 dsh。**
15. **所有成功宣告以真實 E2E Artifact/Golden Job 為準。**

---

# 24. 建議第一批真正開發內容

在本文件核定後，第一批程式碼**不要碰 Harness core**。

第一批只做：

```text
H1 AgentRuntime seam
```

具體工作：

1. 盤點所有直接 new/use `TurnEngine` 的 call site。
2. 定義 `AgentRuntime` contract。
3. 定義 normalized RuntimeEvent。
4. 實作 `NativeRuntime` adapter。
5. 實作 `AgentRuntimeManager`。
6. 把現有 server/session 入口改從 manager 取得 runtime。
7. 預設 runtime 固定 native。
8. 跑所有既有 tests。
9. 跑 RC flow E2E，確認零退化。
10. 更新進度文檔。

只有 H1 全綠，才建立 `harness/` skeleton 進入 H2。

這個順序可以保證：即使 H2/H3 的 Harness integration 失敗，OpenWorker 仍是一個完整可用產品。

---

# 25. 最終判斷

本專案的正確整合方式可以濃縮成一句話：

> **在 OpenWorker repository 中建立受控的 `harness/` integration root，以官方 DeepSeek Harness 為 pinned upstream runtime，先用 profile/plugin/sidecar 方式接入；OpenWorker 先抽出 AgentRuntime seam 並保留 Native TurnEngine，所有 consequential tool 仍經 OpenWorker Permission Gateway，所有正式工程流程仍由 AI-Engineering-OS 管理；只有在 plugin extension 明確不足且真實 Golden Job 證明有必要時，才逐級 patch 或 fork/magic-modify Harness core。**

因此，「把 Harness 放進 OpenWorker 裡面」是對的；但真正應該放進去的是**受控整合層**，不是第一天就把 upstream 原始碼整包複製後到處魔改。
