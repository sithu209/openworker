# OpenWorker「小型 Git 工作帳本」第三批開發進度

> 更新日期：2026-08-17（Asia/Taipei）
>
> 主責 repo：`liuxb99/openworker`
>
> 狀態：`IMPLEMENTING / PROJECT KNOWLEDGE REPLAY WIRED`

## 1. 本批完成內容

第三批把既有 `ProjectKnowledgeStore` 與 `WorkLedger` 接成可恢復的生命週期，而不是要求所有舊 runtime 立即改寫成新 API。

核心策略：

```text
ProjectKnowledgeStore
  append project-knowledge.jsonl
        ↓
JobBinding load / resume / query
        ↓
WorkLedgerBridge.sync_pending_project_events()
        ↓
work-ledger.sqlite revision history
```

只要固定 Job 被重新載入、恢復或查詢，OpenWorker 就會先 replay 尚未同步的 ProjectKnowledge events；成功同步的 event_id 才寫入 sidecar：

`.openworker/work-ledger-project-events.jsonl`

因此若 process 在「ProjectKnowledge 已 append、WorkLedger 尚未同步」之間 crash，下一次 resume 可以補回，不會永久丟失工作 revision history。

## 2. 代碼提交

### 2.1 ProjectKnowledge event → revision lifecycle

`coworker/runtimes/work_ledger_bridge.py`

commit：`98b59be24e57a3ba77f1cbde2d84f5c70360853b`

規則：

- `failed / failure / rework_required` event → HEAD 正式進 `REWORK_REQUIRED`；
- event details 中 `gap_owner_repo / changed_contracts / verification_plan` 寫入返工 provenance；
- HEAD 已 `REWORK_REQUIRED` 時，新的 `progress / repaired / retry` 不得改舊 revision，必須先 `open_rework()` 建 child revision；
- `running / in_progress` → child revision 進 `executing`；
- `completed / success / accepted` 自然語言事件最多把 revision 推到 `verifying`，**禁止自動 accepted**；
- 真正 accepted pointer 仍只能由 WorkLedger required-check gate 更新。

### 2.2 Crash-safe pending event replay

同檔後續 commit：`94b8f47268d9237529f138e2dfb2a83676c17d75`

新增：

- 掃描 `.openworker/project-knowledge.jsonl`；
- 只 replay 尚未記錄的 event_id；
- 成功後 append sidecar；
- malformed JSON / missing event_id fail-closed；
- repeated resume idempotent，不可重複 fork revision。

### 2.3 Job resume 自動同步

`coworker/runtimes/job_binding.py`

commit：`81a67be333daf989f122cf79bfedb47bf85bf245`

現在：

```text
JobBindingStore.load()
→ verify fixed host/workspace
→ ensure WorkLedger
→ replay pending ProjectKnowledge events
→ return binding
```

任何 ledger sync error 都轉為 `JobBindingError`，避免 runtime 在工作歷史不一致時繼續執行。

## 3. Artifact 自動掛載

ProjectKnowledge event 的 `artifact_refs` 若實際指向 workspace 中存在且非空的檔案，bridge 會：

- 計算 SHA256；
- 記 size；
- 記 source event_id；
- 記 capability_id；
- 記 runtime_job_id；
- 掛到目前 HEAD revision。

不存在或空檔案不會被當成 REAL artifact。

同 revision 重複報告同一 logical artifact 不會重複建 tree entry；真正替換 artifact 仍應透過新的 child revision 表達。

## 4. 永久測試

`tests/runtimes/test_job_binding.py`

commit：`3a8473c89dd982bcb6a4032a9c7cf4f8941de6e9`

新增真實 lifecycle 測試：

```text
r1 initial
→ ProjectKnowledge: SceneX reopen failed
→ Job resume
→ r1 = REWORK_REQUIRED
→ ProjectKnowledge: repair running
→ Job resume
→ r2 = rework(parent=r1, rework_of=r1)
→ r2 = executing
→ 再 resume
→ revision 數量仍為 2
```

並驗證 `work-ledger-project-events.jsonl` 只含兩個已同步 event_id，證明 replay idempotent。

## 5. 現在 OpenWorker 已具備的 mini-Git 能力

已完成：

- 每個固定 Job 自動建立 ledger；
- work / revision / parent chain；
- physical artifact tree + SHA256；
- verification checks；
- `REWORK_REQUIRED`；
- owning repo / changed contracts / verification plan provenance；
- fail → child rework revision；
- accepted / delivered protected pointers；
- rollback HEAD 不刪歷史；
- ProjectKnowledge event crash-safe replay；
- repeated resume idempotent。

## 6. 尚未完成的 P0/P1

仍不能把缺口標 CLOSED，因為還差：

1. Final Acceptance 的統一 required-check contract；
2. Case 0003 歷史 REAL evidence baseline importer；
3. Case 0003 UL7 Final Acceptance / reopen workflow；
4. acceptance fail 時自動將具體 failed check、artifact、owning repo 形成返工 request；
5. go-tool-runtime 對 WorkLedger 的正式 query/rework capability；
6. 三台機器/多機 workspace 下 ledger 的持久 authority 設計（不能假設每台 local SQLite 相同）。

## 7. CI

最新測試 commit：

`3a8473c89dd982bcb6a4032a9c7cf4f8941de6e9`

主 CI run：`31985027465`

本文件更新時狀態：`queued`，尚不能宣告 PASS。

## 8. 下一批

下一批直接做 Case 0003 baseline importer + Final Acceptance contract：

```text
歷史 REAL evidence
→ import baseline revision
→ DTM/AOI/Consumer/Blender/SceneX/OS/Delivery required checks
→ OpenWorker UL7 reopen/physical verification
→ PASS: accepted/delivered pointer
→ FAIL: REWORK_REQUIRED → owning repo repair → child revision → rerun
```

這一批完成後，玉井橋才會從「歷史上跑成功」升級成「被新版 OpenWorker mini-Git 治理重新驗收成功」。
