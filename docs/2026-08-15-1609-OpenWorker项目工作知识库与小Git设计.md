# OpenWorker 專案工作知識庫與「小 Git」設計

- 日期：2026-08-15
- 時間：16:09（UTC+8）
- 狀態：DESIGN / IMPLEMENTING
- 目的：讓 OpenWorker 成為每個專案的工作歷史、目前狀態與執行證據權威，讓大模型能直接詢問「專案做到哪了、為什麼這樣做、目前卡在哪、下一步是什麼」。

## 1. 核心定位

OpenWorker 不取代 Git，也不取代 go-tool-runtime。

三者責任固定分離：

- **Git**：原始碼與檔案版本歷史權威。回答 commit、diff、branch、檔案變更。
- **go-tool-runtime**：工具能力與使用知識權威。回答有哪些 capability、工具怎麼用、參數限制、health/status/cancel、成功條件與工具層診斷。
- **OpenWorker**：專案工作歷史與目前執行狀態權威。回答專案做到哪、上一輪做什麼、目前 blocker、決策原因、Job/host/workspace、prompt/execution/artifact evidence、下一步。

OpenWorker 因此類似「專案自己的小 Git」，但版本化的不是只有程式碼，而是**工作狀態與決策歷史**。

## 2. 必須能回答的問題

大模型至少可以直接問：

- 這個專案做到哪了？
- 現在正在做什麼？
- 上一輪完成了什麼？
- 目前卡在哪裡？
- 下一步是什麼？
- 為什麼改成現在這個方案？
- 哪個 host / workspace / OS Job 是正式 binding？
- 最新 execution_id / prompt_id 是什麼？
- 哪些 artifact 已 accepted？哪些 rejected？
- 某次失敗的原因與修復是什麼？
- 哪些缺口還沒關閉？
- 目前 evidence 在哪裡？
- 這個決策是由哪個 owning layer 做的？

查詢不得要求模型先人工翻 GitHub Actions log、Git diff 或大量 MD 才能回答。

## 3. Append-only Project Work Ledger

OpenWorker 必須保存 append-only 工作事件，不只覆寫一份 current status。

建議事件模型：

```text
ProjectWorkEvent
- event_id
- timestamp
- project_id
- job_id
- workspace
- assigned_host
- stage
- status
- event_type
- owner
- capability_id
- summary
- decision
- blocker
- next_action
- execution_id
- prompt_id
- artifact_refs[]
- evidence_refs[]
- git_refs[]
- related_event_ids[]
- details{}
```

事件類型至少包括：

`requirement / plan / decision / dispatch / progress / evidence / failure / diagnosis / repair / retry / qc / accepted / rejected / checkpoint / delivery`

任何 current summary 都應可由 ledger + checkpoint 重建。

## 4. Current Project Snapshot

為了讓查詢快速，OpenWorker 可維護派生 snapshot：

```text
ProjectSnapshot
- project_id
- current_job_id
- assigned_host
- workspace
- current_stage
- current_status
- latest_summary
- active_blockers[]
- accepted_artifacts[]
- rejected_artifacts[]
- latest_execution_id
- latest_prompt_id
- next_actions[]
- open_gaps[]
- updated_at
```

Snapshot 是 cache/派生資料；append-only ledger 才是工作歷史證據。

## 5. Query API / CLI

需要提供給大模型穩定、machine-readable 的查詢入口。

CLI：

```powershell
openworker-project-query --cwd D:\AI-Work\jobs\0002-ALADDIN -q "專案做到哪了？"
openworker-project-query --cwd D:\AI-Work\jobs\0002-ALADDIN -q "目前卡在哪？"
openworker-project-query --cwd D:\AI-Work\jobs\0002-ALADDIN -q "最新 prompt_id 是什麼？"
```

後續 server API：

```text
POST /api/v1/projects/query
GET  /api/v1/projects/{project_id}/snapshot
GET  /api/v1/projects/{project_id}/events
GET  /api/v1/jobs/{job_id}/events
```

Query response 至少包含：

- answer
- project/job identity
- current stage/status
- evidence references
- source event IDs
- confidence/completeness
- next actions（若問題要求）

不得生成沒有 ledger/evidence 支持的專案事實。

## 6. 與 go-tool-runtime 的聯動

標準 AI 工作起點：

1. 先問 OpenWorker：`這個專案做到哪了？`
2. OpenWorker 回 project/job/stage/blocker/next action/evidence。
3. 若下一步需要工具知識，再問 go-tool-runtime：`這個 capability 怎麼用？`
4. go-tool 回 owner、contract、allowed actions、parameter constraints、success criteria。
5. OpenWorker Mission Guard 驗證動作沒有偏離 mission / owner / host / workspace / job。
6. 執行工具。
7. 結果追加回 Project Work Ledger。
8. 失敗時先追加 failure evidence，再 re-query go-tool，得到合法 recovery guidance。
9. retry/repair 也追加 ledger。

因此：

`OpenWorker = 我們現在在哪裡`  
`go-tool = 接下來這個工具應該怎麼正確使用`

## 7. 與防跑偏 Mission Guard 的聯動

每次有副作用的 action 前，Mission Guard 必須比對：

- original goal
- project_id/job_id
- assigned_host/workspace
- current stage
- allowed owner
- allowed capability
- previous accepted evidence
- current blocker
- retry budget

若 action 與目前專案狀態矛盾：

- `ALLOW`：一致，可執行。
- `REQUERY`：資訊不足，先問 OpenWorker project knowledge 或 go-tool。
- `BLOCK`：明確跑偏，例如換 Job、換 host、跨 owning layer workaround、使用 rejected artifact、重跑已 accepted stage。

## 8. Case 0002 實際需求

Case 0002 應自動保存例如：

- 固定 host：DESKTOP-ODAQN0D
- workspace：D:\AI-Work\jobs\0002-ALADDIN
- OS project/job identity
- Studio plan/production queue identity
- 每 shot execution_id / prompt_id
- H3 native 1280×736 與 delivery 1280×720 決策
- stale MP4 rejection 事件
- current-prompt history 驗證
- artifact path/size/mtime/SHA256
- audio/subtitle/QC 狀態
- Final Assembly 狀態
- Delivery Revision / website / final SHA256

例如新的 H3 current-prompt artifact 成功後，不能只留在 Action log；必須追加 ledger event，讓下一個模型直接查得到。

## 9. Persistence

第一階段允許每個固定 workspace 保存：

```text
.openworker/
  mission-contract.json
  mission-checkpoint.json
  project-snapshot.json
  project-events.jsonl
```

後續可同步到 OpenWorker SQLite global index，以便跨 workspace 查：

- 我有哪些 active projects？
- 哪些 project blocked？
- 最近哪個專案剛完成？
- 哪些專案等待人工決策？

workspace ledger 仍保留為 portable/local evidence。

## 10. 與 Git 的關係

ProjectWorkEvent 可保存 `git_refs[]`，例如 commit SHA、branch、repo，但不能把 Git commit 當成「工作已完成」的唯一證據。

例：

- Git commit：修了 H3 canvas contract。
- OpenWorker event：為何修、哪個 failure 觸發、修後哪次 Action 驗證、哪個 artifact accepted。

這就是「小 Git」比普通 Git 多出的工作語意。

## 11. Fail-closed 原則

- 沒有 evidence 的 success 不寫 accepted。
- queued/running 不算 completed。
- API 200 不代表 artifact success。
- stale artifact 不得成為 current evidence。
- rejected artifact 不得被後續 shot/assembly 使用。
- 不允許模型自行改寫歷史事件。
- 修正錯誤時追加 correction/supersede event，不刪舊歷史。
- snapshot 可重建，ledger 不可任意覆寫。

## 12. 第一批實作範圍

P0：

1. `ProjectKnowledgeStore`
2. append-only `ProjectWorkEvent`
3. derived `ProjectSnapshot`
4. `ProjectKnowledgeQuery`
5. `openworker-project-query` CLI
6. Mission Guard 讀 current snapshot 做 drift gate
7. Case 0002 driver 將重要 progress/failure/evidence 寫入 ledger
8. 永久 tests：append-only、query、rebuild、host/job drift、rejected artifact、evidence grounding

P1：

1. FastAPI query endpoints
2. SQLite global project index
3. go-tool failure re-query typed bridge
4. Git refs / Action refs 自動關聯
5. project timeline / diff：`從上次到現在改了什麼？`

## 13. 完成標準

以下情境不需要人工翻 log 即可回答，才算第一階段完成：

```text
Q: 案例 0002 做到哪了？
A: 回答 current stage/status、正式 Job、最新 accepted artifact、active blocker、next action，並附 evidence event IDs。

Q: 為什麼不是 1280×720 直接生成？
A: 回答 H3 32-multiple failure → 1280×736 native → center crop delivery 決策，並指出 failure/decision/verification events。

Q: 上一個 MP4 為什麼不能用？
A: 回答 stale history/provenance rejection，指出 rejected artifact 與 current-prompt acceptance evidence。
```

大模型重啟、換 session、換模型後，仍可從 OpenWorker 恢復正確工作狀態並繼續，不需要依賴聊天記憶。

---

此設計優先於繼續擴充更多零散工具。OpenWorker 若不能可靠回答「專案現在在哪裡」，工具越多，長任務越容易跑偏。