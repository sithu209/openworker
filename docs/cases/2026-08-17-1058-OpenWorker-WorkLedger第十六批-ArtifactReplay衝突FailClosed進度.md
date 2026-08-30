# OpenWorker WorkLedger 第十六批：Artifact Replay 衝突 Fail-Closed 進度

日期：2026-08-17 10:58（Asia/Taipei）

## 本批目標

修補 `WorkLedgerBridge.sync_project_event()` 的通用 replay integrity 缺口。

原行為：

- ProjectKnowledge event 帶 artifact reference。
- Bridge 嘗試把 artifact 加入目前 revision。
- 如果同一 revision 已有相同 `logical_name`，WorkLedger 回報 `already exists in revision`。
- Bridge 只要看到這段訊息就直接吞掉錯誤。
- 沒有比較既有 artifact 與目前 candidate 的 SHA256、size、canonical path。

這會把「同名 artifact 已換 bytes」錯當成正常 idempotent replay，破壞 OpenWorker 的 Git-like revision 不變式。

## 本批修復

### 1. 新增 candidate file identity

`coworker/runtimes/work_ledger_bridge.py` 新增 `_file_identity()`：

- resolve canonical path
- 檢查實體檔存在且非空
- 重新計算 SHA256
- 取得 size_bytes

### 2. 取得 authoritative existing artifact

新增 `_existing_artifact()`：

- 從 WorkLedger snapshot 找到指定 revision。
- 以 logical_name 找 existing artifact。
- 如果 ledger 內同 logical_name 出現多筆，直接視為 ledger invariant broken。

### 3. Duplicate 不再直接吞掉

`sync_project_event()` 遇到 `already exists in revision` 時，現在改呼叫 `_assert_replay_identity()`。

只有以下三個條件全部一致才允許 idempotent skip：

1. `sha256` 完全相同
2. `size_bytes` 完全相同
3. canonical path 完全相同

只要任一不同，拋出：

`ARTIFACT_REPLAY_CONFLICT`

並明確要求建立 child revision 才能代表 replacement bytes。

### 4. 不允許同 revision 偷換成果

新的治理語意：

```text
same revision + same logical_name
        |
        +-- SHA/size/path 全同 -> idempotent replay
        |
        +-- 任一不同 -> ARTIFACT_REPLAY_CONFLICT -> fail-closed
                                        |
                                        +-> create child revision
```

這符合「每個 OpenWorker 工作就是一個工作的 Git」：revision 內既有 artifact identity 不可被後續 replay 偷偷改寫。

## 永久測試

新增：

`tests/runtimes/test_work_ledger_bridge_artifact_replay.py`

目前至少鎖定：

1. 同 path、同 bytes、同 logical_name 重放：只保留一筆 artifact，允許 idempotent replay。
2. 同 logical_name 但 bytes 改變：必須拋 `ARTIFACT_REPLAY_CONFLICT`，既有 ledger artifact SHA 保持不變。

## Commit

核心修復：

`7ed557acbe7ee17f1a55a19f4cc2e39a86de1af0`

永久測試：

`0c030d12ff520fde22b6b7694e139f8373722d27`

## CI

最新完整 CI：

- Run：`31989602021`
- CI #325
- head：`0c030d12ff520fde22b6b7694e139f8373722d27`

本文件建立時三個 job 已啟動，但仍未 terminal：

- pytest：in progress
- gui-unit：in progress
- gui-e2e：in progress

因此本批目前標記為 `IMPLEMENTED — WAITING FOR FULL CI VERIFICATION`，尚未提前宣稱全綠。

## 與三機持久化的關係

這批不是在做三機同步協定本身，但先補掉同步/重放前最基本的資料完整性不變式：

- local SQLite 可以是本機 journal/cache；
- future replication 可以重放 ProjectKnowledge / WorkLedger events；
- 但 replay 絕對不能把同 revision 的 artifact bytes 悄悄改掉。

下一階段才適合在這個 invariant 上建立多機 append-only journal、sync/merge 與 durable authority。
