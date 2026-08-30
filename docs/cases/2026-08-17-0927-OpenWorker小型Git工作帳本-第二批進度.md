# OpenWorker「小型 Git 工作帳本」第二批開發進度

> 更新日期：2026-08-17（Asia/Taipei）
>
> 主責 repo：`liuxb99/openworker`
>
> 狀態：`IMPLEMENTING / DEFAULT JOB LIFECYCLE WIRED`

## 1. 本批目標

上一批已完成通用 `WorkLedger`、revision parent chain、`REWORK_REQUIRED`、acceptance/delivery fail-closed、append-only protection 與 CLI。

本批把它從「可主動使用的元件」提升成 **所有 OpenWorker 固定 Job 的預設生命週期**：任何正式 Job 一旦建立 `JobBinding`，就必須同步建立 `.openworker/work-ledger.sqlite`。若 ledger bootstrap 失敗，JobBinding 也必須失敗並回滾，禁止留下「有工作但沒有工作歷史 authority」的半成品。

## 2. 已完成代碼

### 2.1 WorkLedgerBridge

新增：

`coworker/runtimes/work_ledger_bridge.py`

commit：`78c82065ea29c83d9565da879864c332292b7d57`

目前提供：

- `ensure(binding)`：依 Job Code idempotent 建立/取得 work；
- `snapshot(binding)`：查完整 revision / artifact / check / event history；
- `add_file_artifact(...)`：將真實實體檔案計算 SHA256、size 後掛到 HEAD revision；
- `require_rework(...)`：將目前 HEAD 正式切成 `REWORK_REQUIRED`，保存 reason / owning repo / changed contracts / verification plan；
- `open_rework(...)`：以失敗 revision 為 parent 建新的 child revision，不覆蓋舊成果。

### 2.2 JobBinding 強制 bootstrap mini-Git

修改：

`coworker/runtimes/job_binding.py`

commit：`fa4a79b9104fbc2d17d2b25d84b214958ecef11b`

新的平台 invariant：

```text
create JobBinding
→ write fixed host/workspace binding
→ bootstrap WorkLedger
→ success
```

如果 WorkLedger bootstrap 發生任何錯誤：

```text
ledger bootstrap FAIL
→ remove just-created job-binding.json
→ JobBindingError
→ job creation FAIL
```

因此 OpenWorker 不再允許沒有 revision history 的正式工作存在。

## 3. 永久測試

修改：

`tests/runtimes/test_job_binding.py`

commit：`4e8081719025bea0caa373e6b4643626d63f15ad`

新增永久 invariants：

1. 建立 JobBinding 後 `.openworker/work-ledger.sqlite` 必須真實存在。
2. ledger 必須自動有 initial revision。
3. work code 必須等於 Job Code；workspace 必須等於 fixed workspace。
4. 真實檔案可透過 bridge 登記為 artifact，size / SHA / provenance 寫入 ledger。
5. verification failure 可正式切成 `REWORK_REQUIRED`。
6. rework 必須建立 revision 2，且 `parent_revision_id` / `rework_of_revision_id` 指向失敗 revision。
7. 舊 revision 的 artifact 與失敗狀態必須永久保留。

## 4. 與 ProjectKnowledge / Audit 的責任分工

三者不互相取代：

```text
ProjectKnowledgeStore
= 大模型可讀的工作連續性、目前進度、blocker、next action

AuditStore
= connector/tool action audit trail

WorkLedger
= 工作版本治理 authority：revision / artifact tree / verification / rework / acceptance / delivery
```

下一批要做的是把三者串成同一個 Job lifecycle，而不是刪掉其中任何一層。

## 5. Case 0003 玉井橋的影響

玉井橋 2026-08-16 的 REAL 成功證據仍保留；但新的治理標準下，舊 `current_status=completed` 不再單獨等於 Final Acceptance。

Case 0003 下一步：

1. 將既有 DTM / AOI / Consumer / Blender / SceneX / OS / Delivery evidence 匯入 WorkLedger baseline revision；
2. 為 baseline 建 required checks；
3. 由 OpenWorker 在 UL7 對實體 workspace 做 Final Acceptance / reopen verification；
4. 任一 required check 失敗就正式建立 `REWORK_REQUIRED`；
5. 定位 owning repo、修工具、開 child revision、重跑；
6. 全部通過後才更新 accepted pointer / delivered pointer。

## 6. CI 狀態

前一批 CLI commit `45881bf09fdad3a2cc68b26a86ca242afb10a8bc` 的 CI run `31984806091` 在本次更新時仍為 `in_progress`，不可先算 PASS。

本批最新測試 commit：

`4e8081719025bea0caa373e6b4643626d63f15ad`

GitHub 已建立對應 workflow runs；其中非本功能的 Case 0005 locator workflow 正常 skip，主 CI 尚需 terminal 結果後才能判定本批全綠。

## 7. 下一批 P0

下一批直接補：

- `ProjectKnowledgeStore.record()` → WorkLedger lifecycle bridge；
- artifact_refs 指向實體 workspace 檔案時自動 materialize 到目前 revision；
- `failed/rework_required` knowledge event 自動驅動正式 rework state；
- `repaired/progress` 在 HEAD=`REWORK_REQUIRED` 時必須先開 child revision，禁止改失敗 revision；
- acceptance event 必須由 required checks 驗證後才能移動 accepted pointer；
- Case 0003 baseline evidence importer；
- Case 0003 OpenWorker Final Acceptance workflow。

完成以上後，OpenWorker 的「工作 mini-Git」才會從資料層完整進入日常 runtime 路徑。
