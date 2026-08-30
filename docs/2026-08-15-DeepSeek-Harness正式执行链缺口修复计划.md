# OpenWorker × DeepSeek Harness 正式執行鏈缺口修復計畫

- 日期：2026-08-15
- 狀態：IMPLEMENTING
- 優先級：P0

## 1. 關鍵架構修正

本專案的正式執行邊界不是「Agent 直接在本機自由操作」。

**GitHub self-hosted Action 才是正式的本機執行容器與安全邊界。**

OpenWorker + DeepSeek Harness 的定位是：在固定 self-hosted Action 內提供大模型推理、決策、工具選擇、進度判斷與恢復能力；所有真正會產生副作用的本機操作，仍必須經由 Action 內已啟動、已註冊、可審計的工具鏈執行。

因此不能把 DeepSeek Harness 理解成另一個可任意 shell 操作本機的 agent。

正確模型是：

`GitHub self-hosted Action = 執行容器 / 路由 / 固定主機 / 環境 / 審計邊界`

`OpenWorker = 任務狀態、Job binding、Mission Guard、Permission、Project Knowledge`

`DeepSeek Harness = Action 內的大模型推理 / ACP runtime`

`go-tool-runtime = 工具知識與使用規則權威`

`AI-Engineering-OS / Studio / ComfyX = Action 內允許被調用的正式工具`

## 2. 現行問題

OpenWorker 已有 EngineeringHarnessHost / EngineeringHarnessRuntime / ManagedDeepSeekHarnessRuntime / DeepSeek Harness ACP 正式能力，但案例 0002 現行 REAL V3 在 self-hosted Action 裡仍由 Python driver 直接呼叫 EngineeringOSMediaClient，沒有讓 DeepSeek Harness 成為 Action 內的主要推理 runtime。

所以現在雖然 Action、本機服務、JobBinding、go-tool bootstrap 都存在，但 Action 裡的「大腦」仍是 deterministic Python orchestration，而不是 DeepSeek Harness。

這不能證明完整的：

`使用者要求 → GitHub Action → OpenWorker → DeepSeek Harness → 受控工具 → REAL artifact`

## 3. 正式權威鏈

固定為：

使用者要求
→ GitHub workflow dispatch / trigger
→ Windows self-hosted Action 路由到固定 host
→ 建立固定 workspace / action lock / evidence root
→ 啟動 go-tool-runtime / OS / Studio / ComfyX / ComfyUI
→ OpenWorker EngineeringHarnessHost
→ go-tool-runtime information preflight/query
→ OpenWorker fixed host/workspace/job binding
→ DeepSeek Harness ACP session
→ Harness engineering tool gateway
→ OpenWorker Permission + Mission Guard
→ 只允許調用 Action 內註冊的 AI-Engineering-OS tools
→ OS Project/Job/tool execution
→ Comfyx-Studio story/Bible/shot/Director/ProductionQueue
→ ComfyX / ComfyUI / H3 REAL generation
→ evidence/QC/Final Assembly
→ OS Artifact Registry / Review / Delivery
→ OpenWorker Project Work Ledger
→ Action terminal

**任何本機副作用都不得繞過 self-hosted Action 邊界。**

## 4. V3 的具體缺口

### GAP-HARNESS-0002-01 — Harness 被 Action 內的 Case driver 繞過

現行 `case0002_openworker_source_to_film.py` 在 Action 裡自行完成 go-tool bootstrap、OS Job、source-to-film dispatch 與 terminal wait。

它應降級為 deterministic regression/fallback，不再作為 OpenWorker AI 推理的 primary path。

### GAP-HARNESS-0002-02 — 缺 Harness runtime evidence

REAL Action evidence 至少必須保存：

- github_run_id / job_id
- actual runner name
- assigned_host / workspace
- runtime=engineering-harness
- ACP session_id
- Harness runtime_job_id
- Engineering OS project_id/job_id
- go-tool session_id
- Harness tool call/evidence refs
- Studio queue_id
- ComfyX execution_id/prompt_id
- final artifact provenance

這些 evidence 必須能證明 Harness 是在該次 self-hosted Action 內運行，而不是 Action 外部代理直接操作本機。

### GAP-HARNESS-0002-03 — Runtime 預設與 formal Action 不一致

`RuntimeKind` 目前 Native 是產品預設。正式 Case 0002 workflow 必須在 Action 裡明確啟動 EngineeringHarnessHost，不能依賴隱式 default runtime。

### GAP-HARNESS-0002-04 — Harness 啟動環境沒有被 formal Action 驗證

Formal Action 必須 fail-closed 驗證：

- DeepSeek Harness root
- Node runtime
- Cordis config/plugin
- ACP initialize
- session/new
- session/prompt
- engineering tool ingress
- OS tool manifest

如果其中任一項不存在，Action 必須失敗，不得自動退回 agent 直接 shell 操作本機。

### GAP-HARNESS-0002-05 — Project Knowledge 尚未記錄 Action + Harness 事件

Project Work Ledger 必須同時保存：

- GitHub run/job
- runner/host/workspace
- Harness session/runtime job
- OS Job
- tool call
- failure/repair/retry
- prompt/artifact/QC
- terminal

這樣 OpenWorker 回答「專案做到哪」時，才知道是哪一次正式 Action 做出的結果。

### GAP-HARNESS-0002-06 — 必須禁止 Harness 直接繞過正式工具

DeepSeek Harness 不得因為有本機程序能力就直接：

- 任意修改其他 repo
- 任意啟動未註冊程序
- 直接調 ComfyUI private endpoint 繞過 ComfyX contract
- 直接修改 OS/Studio DB
- 任意換 host/workspace/job
- 使用未經 go-tool / OS manifest 宣告的工具

需要副作用時，只能透過 Action 內的正式 engineering tool gateway。

## 5. 修復策略

### P0-A OpenWorker

1. 增加適合 self-hosted Action 的 non-interactive EngineeringHarnessHost runner。
2. Runner 必須要求現有 JobBinding，或在 Action 內由正式 OS scope 建立後立即固定。
3. 保留 PermissionEngine；Action 模式只允許明確 allowlisted engineering capabilities 自動批准。
4. Mission Guard 在 consequential tool call 前比對 project/job/host/workspace/stage。
5. Harness runtime event 追加到 ProjectKnowledgeStore。
6. TURN_START/TURN_END/ERROR/INTERRUPTED/tool evidence 都寫 ledger。
7. OpenWorker 不提供 unrestricted local shell 作為 Case 0002 recovery path。

### P0-B GitHub self-hosted Action

1. 新建 REAL V4 Harness workflow，不破壞 V3 deterministic regression。
2. 固定 `DESKTOP-ODAQN0D` + `D:\AI-Work\jobs\0002-ALADDIN`。
3. 保留 Action lock，禁止同一正式 workspace 有第二個 production worker。
4. Action 先 checkout/build/啟動所有受控服務。
5. Action 內明確啟動 DeepSeek Harness 所需 Node/Cordis/ACP 環境。
6. 最後才啟動 OpenWorker EngineeringHarnessHost。
7. 不讓外部 agent 直接接管本機程序。

### P0-C Case 0002

1. 不再由 Python driver primary orchestration 整條 source-to-film。
2. Action 把 `TASK.md` / mission / expected deliverables 交給 OpenWorker。
3. DeepSeek Harness 在 Action 內判斷下一步。
4. 需要工具時查 go-tool，再透過 OpenWorker engineering tool gateway 呼叫 OS。
5. failure → Project Ledger → go-tool re-query → Mission Guard → 合法 retry。
6. 最終仍由 Action 收集 evidence 與 terminal status。

### P0-D 驗證

必須證明：

1. GitHub self-hosted Action 是正式外層執行容器。
2. runner 真的是 assigned host。
3. go-tool preflight 在 OS execution 前。
4. Harness ACP session 在該次 Action 中真實建立。
5. Harness runtime job 與 OS Job 關聯。
6. Harness 真實取得 OS tool manifest。
7. source-to-film tool call 從 Harness → engineering gateway → OS 發出。
8. 不存在 Harness 直接 shell/HTTP 繞過正式工具鏈的 production 證據。
9. H3 prompt/artifact provenance 對應 current prompt。
10. Project Knowledge 可回答 current Action run、stage、blocker、next action、runtime_job_id、prompt_id。

## 6. Python Case Driver 的新定位

保留 `case0002_openworker_source_to_film.py`，但定位改為：

- deterministic integration regression
- OS/Studio/ComfyX contract smoke
- Harness 路徑故障時的診斷對照

它仍可在 self-hosted Action 中跑，但它的成功不能單獨代表「OpenWorker + DeepSeek Harness AI worker 閉環」。

## 7. Project Knowledge 的正確定位

OpenWorker Project Knowledge 必須把 Action 也視為工作身份的一部分。

建議每個重要事件包含：

```text
github_run_id
github_job_id
runner_name
assigned_host
workspace
harness_session_id
runtime_job_id
os_project_id
os_job_id
capability_id
execution_id
prompt_id
artifact_refs
evidence_refs
```

因此之後大模型問：

`這個專案做到哪了？`

OpenWorker 可以回答：

`正式 run 318... 在 DESKTOP-ODAQN0D 上完成 shot-1；Harness runtime_job=...；OS job=...；H3 prompt=...；artifact 已 accepted；下一步是 shot-2。`

而不是只回答一份脫離 Action 的 agent session 狀態。

## 8. 2026-08-15 本批實作進度

### 已實作

1. **Project Knowledge 單一權威已收斂**
   - 正式實作固定為 `coworker/runtimes/project_knowledge.py`。
   - 刪除重複的 `coworker/project_knowledge.py` 與 `project_query_cli_v2.py`，避免兩套 ledger/CLI 漂移。
   - append-only event 現在具有穩定 `event_id`。

2. **Harness runtime evidence 已加強**
   - `ManagedDeepSeekHarnessRuntime` 的 TURN_START / TURN_END / INTERRUPTED 現在會帶出 `session_id`、`runtime_job_id`、`engineering_job_id`、`project_id`。
   - health 也會回報真實 `session_id`，不再只提供 `session_created=true`。

3. **Project Knowledge 已能保存 Harness 與 artifact provenance**
   - runtime
   - session_id
   - runtime_job_id
   - execution_id
   - prompt_id
   - artifact_refs
   - artifact_disposition=accepted/rejected
   - accepted/rejected artifact snapshot

4. **Self-hosted Action Harness 模式已加入 fail-closed allowlist**
   - `openworker-engineering --action-mode`
   - 必須至少提供一個精確 `--allow-tool`。
   - `--action-mode` 禁止與 unrestricted `--auto-approve` 同時使用。
   - 未列入 allowlist 的 consequential tool 一律 `DENY`。
   - 不提供 unrestricted shell recovery。

5. **Harness event → Project Work Ledger 已接入**
   - TURN_START → dispatch event
   - TOOL_STARTED / TOOL_FINISHED → tool events
   - ERROR → failure/blocker
   - INTERRUPTED → interrupted
   - TURN_END → completed/failure

6. **永久測試已新增**
   - exact tool allowlist
   - shell/相似名稱拒絕
   - Action mode 無 allowlist fail-closed
   - Action mode + unrestricted auto approve fail-closed
   - Project ledger append-only
   - Harness session/runtime job query
   - stale artifact rejected / current artifact accepted

### CI 狀態

最新 push `6d15a35bc42bbdb849064af31c7f08e0c376f37e` 已自動觸發：

- CI run `31874306103`
- Engineering H11 Workspace Bootstrap Win11 run `31874306131`

建立本進度記錄時兩者仍為 queued/pending，因此本批目前只能標記 **IMPLEMENTED / VERIFYING**，不能標記 VERIFIED。

### 尚未完成

1. REAL V4 workflow 尚未建立。
2. Case 0002 尚未由 self-hosted Action 內的 DeepSeek Harness primary path 重跑。
3. Mission Guard 尚未插到每一個 consequential engineering tool call 前做 action-level gate。
4. GitHub run/job/runner identity 尚未自動寫入每一個 Project Knowledge event。
5. go-tool failure re-query → legal retry 尚未與 Harness Action path 完整串通。
6. Final REAL evidence 還沒有證明 `Action → Harness → OS tool → Studio → ComfyX → H3 artifact` 全鏈。

## 9. 下一批

下一批按此順序執行：

1. 等本批 CI terminal，先修任何 regression。
2. 將 Mission Guard 接到 Action Harness consequential tool approval/gateway。
3. 將 GITHUB_RUN_ID / GITHUB_JOB / RUNNER_NAME / COMPUTERNAME 自動寫入 ledger details/evidence。
4. 建立 AI-Engineering-OS `Case 0002 REAL V4 Harness` workflow。
5. V4 只允許所需 OS engineering tools，不允許 shell 兜底。
6. 在固定 ODAQ runner 真跑一次 DeepSeek Harness ACP + Case 0002。
7. 依 REAL failure 修 owning layer，再更新本文檔。

## 10. 完成標準

只有 REAL V4 evidence 同時存在以下鏈才可關閉缺口：

`GitHub self-hosted Action → fixed runner/workspace → go-tool session → OpenWorker binding → Harness ACP session → Harness runtime_job → OS job → Harness engineering tool call → Studio queue → ComfyX execution/prompt → current artifact → QC/final delivery → Project Work Ledger → Action terminal`

任何一段缺失都維持 IMPLEMENTING。
