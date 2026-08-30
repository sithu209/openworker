# OpenWorker × DeepSeek Harness 結合研究

> 狀態：**RESEARCH / ARCHITECTURE STUDY ONLY**  
> 日期：2026-08-14  
> OpenWorker 研究基線：`engineering-e6-4-public-api-e2e` / `2526b92e910681482507146801e0106819008b21`  
> DeepSeek Harness：`deepseek-ai/deepseek-harness`，目前為 **Developer Preview**  
> 本文件只做架構研究與後續實驗設計，**尚未開始修改 Agent runtime、生產整合或切換預設引擎**。

---

## 1. 研究目的

OpenWorker 已經具備完整的「AI coworker 產品層」：Desktop/Web UI、Connector、MCP、Memory、Automation、Session、Permission/Approval、多模型 Provider，以及工程能力入口。另一方面，DeepSeek Harness（`dsh`）提供 plugin-first 的 Agent Harness：Agent Loop、Tool Registry、Session Log、LLM Adapter、Jobs、Sandbox、Approval Policy 等幾乎全部能力都可透過 Cordis plugin 替換。

兩者有大量能力重疊，因此不能直接把 Harness「塞進」OpenWorker；必須先決定責任邊界，避免形成兩套 Agent Loop、兩套 Tool Registry、兩套 Session/Memory、兩套 Approval 與兩套工程 Workflow。

本研究要回答：

1. Harness 應該接在 OpenWorker 哪一層？
2. 哪些能力應由 OpenWorker 保留，哪些能力可交給 Harness？
3. OpenWorker 現有 agent engine 是否應直接被替換？
4. 如何保留現有 Permission / Approval / Automation / Memory / UI？
5. 如何繼續讓 AI-Engineering-OS 成為工程 Workflow 與工程 Tool Contract 的唯一權威？
6. 如何在不破壞既有 OpenWorker 的前提下，以 A/B 方式驗證 Harness 是否真的更好？

---

## 2. 目前 OpenWorker 的真實架構

本研究不是以 `main` 為準，而是以目前工程整合最完整的 stacked branch：

```text
engineering-e6-4-public-api-e2e
2526b92e910681482507146801e0106819008b21
```

原因是 OpenWorker 的 E1～E6.4 工程整合目前仍位於連續 draft PR 分支，`main` 尚未包含完整的 OS-managed engineering flow。

### 2.1 TurnEngine 已經是 OpenWorker 自己的 Agent Loop

`coworker/engine.py` 的 `TurnEngine` 目前負責：

- 一個 user turn 內的多輪 model ↔ tool iteration；
- streaming；
- tool call 執行；
- parallel low-risk tool execution；
- permission decision 與 user approval；
- interrupt；
- steering；
- retry；
- durable resume；
- compaction；
- message history；
- tool-call orphan 修復；
- turn / iteration event 輸出。

因此它不是一個薄薄的 provider wrapper，而是 OpenWorker 現有 Agent Runtime 的核心。

### 2.2 ProviderClient 只負責「單次模型呼叫」

`coworker/providers/base.py` 明確把 `ProviderClient` 定義成 single-shot completion interface，並特別註明：

```text
without a max_turns loop — the runtime owns the agent loop
```

這是一個重要判斷：**DeepSeek Harness 不應只被包成新的 ProviderClient。**

若只把 Harness 放在 Provider 層，Harness 最有價值的 Agent Loop、Session、Tool Pipeline、Job lifecycle、plugin interception 等能力都用不到，最後只會得到另一個昂貴且重疊的 LLM adapter。

### 2.3 OpenWorker ToolRegistry 是 runtime-owned registry

`coworker/tools/registry.py` 目前負責：

- Python callable → OpenAI function schema；
- tool name → callable；
- tool schema 提供給模型；
- tool execute。

Permission 不在 registry 裡，而是由 TurnEngine + PermissionEngine 控制。

這個分離是正確的，也讓 Harness integration 有清楚的橋接點：Harness 可以「看見」OpenWorker tools，但真正執行時仍應經過 OpenWorker 的 permission boundary。

### 2.4 Permission / Approval 是 OpenWorker 的產品安全邊界

`coworker/permissions.py` 已經有：

- Discuss / Plan / Interactive / Auto / Custom mode；
- read-only enforcement；
- path scope；
- shell command allowlist；
- session allowlist；
- automation task-scoped standing rules；
- external-risk / write / exec 分級；
- consequential operation 必須 ask-user。

這些規則直接跟使用者 UI、Workspace、Automation、Connector、安全語意綁定。

**結論：Harness 不可繞過 OpenWorker PermissionEngine。**

即使 Harness 自己也有 sandbox / approval policy，OpenWorker 的 user-level approval 仍應是產品層權威；Harness policy 可以作為內層防線，但不能成為 bypass OpenWorker approval 的替代品。

### 2.5 Desktop 已經有 managed-sidecar 模式

`surfaces/gui/src-tauri/src/lib.rs` 現在由 Tauri：

1. 選一個 localhost free port；
2. 啟動 Python `openworker-server` managed sidecar；
3. 注入 HTTP/WS endpoint 與 per-launch auth token；
4. app quit 時管理 sidecar lifecycle；
5. sidecar 有自己的 log 與 production/dev binary resolution。

因此 OpenWorker 已經有成熟的「Desktop shell 管理外部 runtime process」模式。

這對 Harness 很重要，因為 dsh 是 Node/TypeScript/Cordis 生態。第一版沒有必要把它重寫成 Python，也沒有必要硬嵌進 OpenWorker process；**local sidecar / child-runtime 是風險最低的原型路線。**

### 2.6 工程 Workflow 已經明確委派給 AI-Engineering-OS

目前 `coworker/engineering/flow_client.py` 的公開 `EngineeringOSFlowClient.execute_rc_column_flow()` 直接呼叫：

```http
POST /api/v1/jobs/{job_id}/flows/rc-column
```

而且原始碼註解明確寫：

```text
The underlying workflow remains authoritative in AI-Engineering-OS.
```

所以 Harness integration 不應改變這個原則。

---

## 3. DeepSeek Harness 真實架構

DeepSeek 官方 repository：

```text
https://github.com/deepseek-ai/deepseek-harness
```

README 目前把 dsh 定位成 DeepSeek AI 開發的 open-source agent harness，核心原則是：

```text
everything is a plugin
```

底層使用 Cordis。官方同時明確標示目前為 **Developer Preview**，並警告會有 compatibility-breaking changes。

### 3.1 dsh 不是單純的 LLM SDK

依官方 `docs/architecture.md`，以下全部都是 plugin / replaceable capability：

| Harness subsystem | Context key |
|---|---|
| Session event log | `ctx.sessions` |
| System prompt / tool schema assembly | `ctx.systemPrompt` |
| Tool registry + guarded execution pipeline | `ctx.tools` |
| Agent registry | `ctx.agents` |
| Default agent loop | `ctx.agentLoop` |
| LLM adapter seam | `ctx.llm` |

此外還有 jobs、filesystem、shell、sandbox、subagent、commands、goals、session title、UI integration 等 extension seams。

因此 Harness 的價值本質上位於 **Agent Runtime / Orchestration 層**，而不是 Provider 層。

### 3.2 Session Log 是 Harness 的模型上下文來源

Harness 的設計原則是：

```text
Model-visible means logged.
```

model history 從 durable SessionEvent log 投影產生；fork、resume、transcript、telemetry、persistence 也都從這個 event stream 衍生。

這和 OpenWorker 現有 durable conversation / message / resume 機制會直接重疊，是整合時最需要避免「雙主資料庫」的地方之一。

### 3.3 Harness Tool Pipeline 比一般 tool registry 更深

Harness turn flow 包含：

```text
agent/request
  -> llm/stream
  -> assistant/message
  -> tool/call
  -> tools/pre-execute
  -> tools/execute
  -> tools/post-execute
  -> tool/result
```

而且 `agent/*`、`tools/*` 可被 plugin 攔截。

這正是 Harness 比「另一個 model provider」更有價值的部分。

### 3.4 Harness 原生支援 background jobs

官方 architecture 建議 background work register 到 `ctx.jobs`，再由 `job_*` tools collect / stop。

OpenWorker 本身也有 Automation、長任務、interrupt/resume，因此後續必須設計 job ownership，而不能讓同一個工作同時被兩個 scheduler/runtime 管理。

---

## 4. 最重要的責任邊界

建議的長期三層：

```text
User / Desktop / Web / Connector / Telegram
                    │
                    ▼
              OpenWorker
  ┌──────────────────────────────────┐
  │ Product / Human Interaction Layer│
  │ UI · Connector · Memory          │
  │ Automation · Permission/Approval │
  │ User Session · Finished-work UX  │
  └────────────────┬─────────────────┘
                   │ AgentRuntime seam
                   ▼
            DeepSeek Harness
  ┌──────────────────────────────────┐
  │ Agent Runtime / Orchestration    │
  │ Agent Loop · Tool Dispatch       │
  │ Context · Jobs · Plugin Runtime  │
  │ Planning · Subagents · Recovery  │
  └────────────────┬─────────────────┘
                   │ engineering tools / flows
                   ▼
          AI-Engineering-OS
  ┌──────────────────────────────────┐
  │ Engineering Control Plane        │
  │ Canonical Tool Contract · Recipe │
  │ Job · Artifact · Review/Approval │
  │ Delivery · Digital Thread        │
  └────────────────┬─────────────────┘
                   ▼
   ComfyX / Design Forge / DWG / Terrain / BIM / ...
```

### 4.1 OpenWorker 應保留

OpenWorker 應繼續擁有：

- Desktop / Web / Connector surfaces；
- 使用者 identity / workspace / folders；
- 使用者長期 memory；
- Automation schedule 與 task ownership；
- user-facing Permission / Approval；
- UI transcript / notifications / finished deliverable UX；
- connector credentials；
- runtime selection/configuration；
- AI-Engineering-OS client / engineering facade。

### 4.2 Harness 應逐步承擔

若 A/B 驗證證明更成熟，可由 Harness 承擔：

- agent loop；
- context assembly / model-facing turn state；
- tool selection / dispatch orchestration；
- agent-step lifecycle；
- planning / subagent orchestration；
- background runtime jobs；
- runtime recovery / continuation；
- LLM adapter plugin composition。

### 4.3 AI-Engineering-OS 必須繼續擁有

- canonical engineering tool IDs / schemas；
- engineering recipes / workflows；
- engineering Job lifecycle；
- engineering Artifacts；
- calculation / drawing / BIM workflow；
- engineering review / approval / publish / delivery semantics；
- Digital Thread / provenance；
- specialist engine routing。

**Harness 不得重新實作工程 workflow。OpenWorker 也不得成為第二個 Engineering Workflow Engine。**

---

## 5. 不應採用的整合方式

### 5.1 不建議：Harness 只做 ProviderClient

```text
TurnEngine -> HarnessProvider -> dsh -> model
```

缺點：

- OpenWorker 自己仍跑完整 Agent Loop；
- Harness 自己的 Agent Loop / tool pipeline / session / jobs 幾乎全部浪費；
- 多一層 abstraction，卻沒有取得 Harness 的主要收益。

可以作為很短的 connectivity smoke，但不應是正式架構。

### 5.2 不建議：把 Harness 的 TypeScript 核心重寫成 Python

這會造成：

- 大量 fork 成本；
- 與 DeepSeek upstream 快速脫節；
- Developer Preview 每次 breaking change 都要人工 port；
- Cordis plugin 生態失去意義。

### 5.3 不建議：OpenWorker 與 Harness 各自獨立接 OS

```text
OpenWorker ──> OS
Harness    ──> OS
```

這可以當獨立產品，但不是「OpenWorker 結合 Harness」。

使用者會得到兩個 Agent 入口、兩套 session、兩套 approval、兩套 UX，沒有形成一個完整 AI coworker。

### 5.4 不建議：Harness 直接呼叫 consequential tools，跳過 OpenWorker PermissionEngine

這會破壞 OpenWorker 已經存在的：

- path scope；
- shell approval；
- task standing rule；
- connector target approval；
- Discuss / Plan / Interactive / Auto mode。

因此所有由 Harness 發動的 OpenWorker-owned consequential tool，最終執行前仍必須通過 OpenWorker permission gateway。

---

## 6. 建議方案：Optional Harness AgentRuntime Backend

### 6.1 第一階段不是替換，而是增加 seam

長期程式結構建議：

```text
OpenWorker
    │
    ▼
AgentRuntime
    ├── NativeRuntime / LegacyTurnEngine
    │       └── 現有 coworker.engine.TurnEngine
    │
    └── DeepSeekHarnessRuntime
            └── local dsh sidecar / plugin profile
```

在 A/B 完成以前：

- Legacy TurnEngine 保留；
- Harness runtime 為 opt-in；
- 不改預設值；
- 同一個 Golden Job 可以指定 runtime；
- 對外 UI/event contract 儘量保持一致。

### 6.2 第一版推薦 Sidecar，而不是 in-process

建議拓撲：

```text
Tauri Desktop
   │
   ├── managed openworker-server (Python)
   │        │
   │        └── AgentRuntime client
   │
   └── managed dsh runtime (Node.js)
            │
            └── OpenWorker bridge plugin
```

或先更保守：由 Python server 在需要 Harness runtime 時 spawn dsh child process，由 Tauri 暫時只管理 Python server。

選擇 sidecar 的理由：

1. 保留 dsh upstream 原生 TypeScript/Cordis；
2. 不需 fork/rewrite；
3. 可以 pin Harness version；
4. crash 可以隔離；
5. 可獨立更新；
6. OpenWorker 已有 managed sidecar 實務；
7. A/B 時可隨時退回 NativeRuntime。

---

## 7. OpenWorker ↔ Harness 的橋接設計

以下是研究階段的 design sketch，不是已承諾 API。

### 7.1 Runtime lifecycle

OpenWorker 需要一個穩定 runtime contract，大致涵蓋：

```text
start_session
run_turn
stream_events
interrupt
resume
steer
close_session
health
```

不要讓 UI 直接理解 Cordis internals；UI 應只看到 OpenWorker 自己的穩定 event vocabulary。

### 7.2 Tool bridge

Harness 可以把 OpenWorker tools 註冊成 `ctx.tools` capability，但 tool execution 不直接拿 Python callable，而是呼叫 OpenWorker Tool Gateway：

```text
Harness model
   ↓
ctx.tools
   ↓
OpenWorker bridge plugin
   ↓
OpenWorker Tool Gateway
   ↓
PermissionEngine
   ↓ allow / approval / deny
ToolRegistry.execute()
   ↓
result
```

如此可以取得 Harness tool pipeline 的好處，同時保留 OpenWorker 現有安全模型。

### 7.3 OS tool bridge

工程工具不要在 Harness 中手抄 schema。

應由 AI-Engineering-OS canonical discovery/API 動態產生可用工程 tools，再透過 OpenWorker/OS bridge 暴露給 Harness。

原則：

```text
OS schema = source of truth
Harness tool = projection / adapter
OpenWorker engineering facade = product integration boundary
```

### 7.4 Approval 必須分成兩層

不能把兩種 approval 混為一談：

**A. OpenWorker user-action approval**

例如：

- shell command；
- 寫檔；
- 寄信；
- 發布外部內容；
- connector side effect。

由 OpenWorker PermissionEngine / UI 掌權。

**B. AI-Engineering-OS engineering governance**

例如：

- Calculation reviewed；
- Drawing approved；
- BIM completeness；
- publish/delivery gate。

由 OS 掌權。

Harness 只是 runtime，不能自己宣布任何一層 approval 已通過。

---

## 8. Session / Memory：避免雙主資料源

這是整合最大風險之一。

OpenWorker 已有 conversation/session/memory/durable-resume；Harness 也以 SessionEvent log 為模型上下文 source of truth。

不建議兩邊各自保存一份「完整且都自稱 canonical」的長期對話。

### 建議原則

**OpenWorker = durable product/user record authority**  
**Harness Session = runtime projection / execution record**

也就是：

```text
OpenWorker durable conversation
       │
       ├─ materialize/runtime projection ──> Harness session
       │
       └─ consume runtime events <───────── Harness
```

Harness 為了 replay / resume 可以保存自己的 session log，但 OpenWorker 必須保存可以重建產品 transcript、approval、task、artifact reference 的 canonical product state。

後續需要設計穩定的 correlation IDs：

```text
openworker_session_id
runtime_session_id
turn_id
step_id
tool_call_id
job_id
engineering_job_id
artifact_id
```

---

## 9. Jobs / Cancellation Ownership

Harness 官方已有 `ctx.jobs`；OpenWorker 也有 Automation、running turn interrupt 與 durable resume。

應分清：

### OpenWorker Automation

負責「什麼時間啟動工作」：

```text
every morning
at 09:00
when scheduled task fires
```

### Harness Job

負責「這次 Agent execution 裡的 background work」：

```text
long tool execution
subagent
background computation
runtime-owned continuation
```

### AI-Engineering-OS Job

負責「工程工作的正式 domain lifecycle」：

```text
Project / Job / Task / Stage / Artifact / Review / Delivery
```

三者不要合併成一個巨大 Job object，而應透過 ID correlation 串起來。

Cancellation 也應逐層傳遞：

```text
User Stop
  -> OpenWorker runtime cancel
     -> Harness agent/job cancel
        -> active tool cancel
           -> OS job/tool cancellation（若該 operation 支援）
```

每層都要回傳實際取消結果，不能只把 UI 標成 cancelled。

---

## 10. UI / Streaming / Event Mapping

OpenWorker 現有 UI 不應依賴 Cordis event 名稱。

建議 Harness bridge 將：

```text
turn/start
step/start
assistant/chunk
tool/call
tool/result
step/end
turn/end
agent status / job status
```

映射成既有或擴充後的 OpenWorker `EventType`。

好處：

- NativeRuntime 與 HarnessRuntime 使用同一套 UI；
- A/B 不必寫兩套前端；
- Harness breaking changes 只影響 adapter；
- Connector surface 也不用知道後端 runtime 是誰。

---

## 11. Packaging / Versioning

Harness 目前官方明確標示 Developer Preview 且會有 breaking changes。

因此正式整合前必須：

1. pin 精確 npm package / Git commit；
2. 不允許 production app 啟動時自動拉 `latest`；
3. bridge protocol 自己 version；
4. capability handshake；
5. Harness 啟動失敗時可 fail back 到 NativeRuntime；
6. sidecar log 與 health probe；
7. Windows/macOS/Linux 分別驗證 packaging；
8. 升 Harness 版本必須重跑 Golden Job A/B suite。

不建議現階段把 dsh runtime 變成不可替代的唯一 boot dependency。

---

## 12. 建議的實驗路線

### P0 — Research / Contract（本文件）

- [x] 讀 OpenWorker 現有 TurnEngine / Provider / ToolRegistry / Permission；
- [x] 讀 Desktop managed-sidecar；
- [x] 讀現有 OS-managed engineering flow；
- [x] 讀 DeepSeek Harness 官方 README / architecture；
- [x] 定義 responsibility boundary；
- [ ] 尚未改 runtime code。

### P1 — Harness sidecar smoke

目標只有：

```text
OpenWorker -> start dsh -> health -> one text turn -> stop
```

不接 tools、不接 OS、不改預設 runtime。

成功條件：

- deterministic start/stop；
- crash 不拖垮 OpenWorker；
- health/version/capabilities 可讀；
- stdout/stderr/log 可追蹤。

### P2 — AgentRuntime abstraction

建立最小 runtime seam：

```text
NativeRuntime
HarnessRuntime
```

同一 UI 可以跑純文字 turn。

### P3 — OpenWorker tool + approval

只接一個 read tool 與一個 consequential tool。

必須證明：

- Harness 能選 tool；
- consequential tool 一定經 PermissionEngine；
- deny 真正阻止 execution；
- approve 後只執行一次；
- interrupt 不留下 orphan tool call。

### P4 — AI-Engineering-OS discovery/invoke

讓 Harness 經 OpenWorker bridge 使用 OS engineering capability。

禁止手工複製 OS schema。

### P5 — RC Column Golden Job A/B

直接使用現有 E6.4 真實鏈：

```text
readiness
 -> Project
 -> Job
 -> OS RC flow
 -> calculation
 -> drawing
 -> BIM
 -> completeness
 -> review
```

NativeRuntime 與 HarnessRuntime 跑同一輸入。

### P6 — Reliability

測：

- stop mid-stream；
- stop mid-tool；
- permission wait 後 restart；
- Harness crash；
- OpenWorker restart；
- OS temporary failure；
- duplicate tool-call prevention；
- durable resume；
- long-running job correlation。

### P7 — 決策是否升為 default runtime

只有當 Harness 在真實 Golden Jobs 有明顯收益，才討論 default switch。

---

## 13. A/B 評估指標

不能只看「能不能跑完」。至少記錄：

| 指標 | NativeRuntime | HarnessRuntime |
|---|---:|---:|
| Golden Job success | | |
| Tool selection correctness | | |
| Wrong/redundant tool calls | | |
| Approval bypass count | | |
| Duplicate side effects | | |
| Artifact completeness | | |
| Engineering workflow correctness | | |
| Interrupt latency | | |
| Resume success | | |
| Crash recovery | | |
| Total wall time | | |
| Model input/output tokens | | |
| Cache effectiveness | | |
| Human intervention count | | |
| Final deliverable quality | | |

是否採用 Harness，要由這些實際數據決定，而不是只因為它是新的 Agent framework。

---

## 14. 主要風險

### R1 — 兩套 Agent Loop 都在工作

**風險：** tool call 重複、history 不一致、interrupt ownership 不清。  
**對策：** 每個 session 只能有一個 active AgentRuntime。

### R2 — Approval bypass

**風險：** Harness 直接執行 OpenWorker consequential tool。  
**對策：** bridge execution endpoint 強制走 PermissionEngine；不能靠 prompt 約束。

### R3 — Session dual-write drift

**風險：** OpenWorker transcript 與 Harness session log 分叉。  
**對策：** 定義 canonical product record + runtime projection + correlation IDs。

### R4 — Harness Developer Preview breaking changes

**對策：** pin version、adapter contract、compatibility tests、fallback runtime。

### R5 — OpenWorker 被改造成 dsh fork

**對策：** Harness 保持 upstream sidecar/plugin；OpenWorker 只擁有 adapter。

### R6 — Harness/OpenWorker 複製 OS engineering workflow

**對策：** OS 仍是唯一 engineering workflow authority；Golden Path 只呼叫 OS public flow/tool APIs。

### R7 — 打包體積與 Node runtime

**對策：** P1 先開發環境 sidecar；確認收益後才決定 bundled Node、standalone binary 或其他 distribution。

---

## 15. 初步決策

### 建議採用

**OpenWorker Product Shell + Optional DeepSeek Harness AgentRuntime + AI-Engineering-OS Engineering Control Plane**

而且採漸進式：

```text
現在：
OpenWorker -> Native TurnEngine -> OS/tools

第一階段：
OpenWorker -> AgentRuntime
                 ├─ Native TurnEngine (default)
                 └─ Harness sidecar (experimental)

驗證成功後：
OpenWorker -> HarnessRuntime (candidate default)
              └─ OpenWorker Permission/Tool bridge
                    └─ AI-Engineering-OS
```

### 現階段明確不做

- 不刪 `TurnEngine`；
- 不把 Harness 設成 default；
- 不重寫 dsh；
- 不把 dsh 當單純 ProviderClient；
- 不改 OS workflow authority；
- 不讓 Harness bypass OpenWorker approval；
- 不把兩套 session 都當 canonical；
- 不因研究文檔就宣稱整合完成。

---

## 16. 最終研究結論

OpenWorker 與 DeepSeek Harness **適合結合**，但最佳結合點不是模型 Provider，也不是把兩個產品平行放在 OS 前面，而是：

> **讓 OpenWorker 保留 AI coworker 的產品外殼與人機治理，讓 DeepSeek Harness 成為可替換的 Agent Runtime，讓 AI-Engineering-OS 繼續做工程能力與 Workflow 的唯一權威。**

這個方向同時保留三個專案最有價值的部分：

- OpenWorker：成熟的人機介面、Connector、Permission、Automation、Memory、Desktop UX；
- DeepSeek Harness：plugin-first Agent Loop、tool pipeline、session/runtime lifecycle、jobs、可替換 capability seams；
- AI-Engineering-OS：工程語意、工程流程、Artifact、Review/Delivery、Digital Thread。

下一個合理步驟不是全面移植，而是 **P1：建立完全可移除、預設關閉的 Harness local sidecar smoke prototype**。只有在 RC Column Golden Job 等真實 A/B 證明 Harness 在可靠性、工具選擇、長任務、恢復或效率上有實質提升後，才進一步決定是否取代 Native TurnEngine。

---

## 參考原始碼 / 文件

### OpenWorker

- `coworker/engine.py`
- `coworker/providers/base.py`
- `coworker/tools/registry.py`
- `coworker/permissions.py`
- `surfaces/gui/src-tauri/src/lib.rs`
- `coworker/engineering/flow_client.py`
- `coworker/engineering/e2e_verify.py`
- `docs/engineering/managed-rcflow.zh-TW.md`
- `docs/engineering/e2e-verification.zh-TW.md`

### DeepSeek Harness

- `deepseek-ai/deepseek-harness/README.md`
- `deepseek-ai/deepseek-harness/docs/architecture.md`
- `deepseek-ai/deepseek-harness/docs/subsystems/core.md`
- `deepseek-ai/deepseek-harness/docs/subsystems/tools.md`
- `deepseek-ai/deepseek-harness/docs/subsystems/session.md`
- `deepseek-ai/deepseek-harness/docs/tool-execution-pipeline.md`

