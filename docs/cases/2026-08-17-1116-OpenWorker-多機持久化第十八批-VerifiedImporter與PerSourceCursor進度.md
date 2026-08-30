# OpenWorker 多機持久化第十八批：Verified Importer 與 Per-Source Cursor 進度

時間：2026-08-17 11:16 +08:00

## 本批目的

在第十七批每台機器獨立 hash-chained append-only journal 的基礎上，補上接收端的 verified importer。目標不是現在就把三台 SQLite 強行合併，而是先建立可驗證、可續傳、可重放且 fail-closed 的來源匯入 contract。

## 已完成

### 1. `coworker/work_sync_importer.py`

新增 `WorkSyncImporter`：

- 每個 `source_host` 使用獨立 durable cursor。
- cursor 記錄 `source_sequence + event_hash`。
- 匯入前先讓 `WorkSyncJournal.read_all()` 驗證完整 source hash chain。
- 已匯入 prefix 必須與 durable cursor 的 sequence/hash 完全一致。
- source journal 比 cursor 短：`SOURCE_TRUNCATION`，fail-closed。
- 同 sequence 但 hash 不同：`SOURCE_FORK`，fail-closed。
- 只套用 cursor 之後的 unseen events。
- 每一筆 event 的 `apply_event` 成功後才 atomic 推進 cursor。
- 再次匯入完全相同 journal 時 `imported_events=0`，不重複套用。

實作 commit：`31c437edcc155bb1b078f16b40b1747c344ee3bf`

### 2. 永久測試

新增 `tests/test_work_sync_importer.py`：

- 初次匯入 2 筆 → cursor 到 sequence 2。
- 同 journal 再匯入 → 0 筆，idempotent。
- source append 第 3 筆 → 只匯入 delta 1 筆。
- 已匯入後，來源改成另一條「本身仍合法」但不同 hash 的歷史 → `SOURCE_FORK`。
- 已匯入到 sequence 2，來源縮短成 sequence 1 → `SOURCE_TRUNCATION`。

測試 commit：`6f925131681d76a80dd578d272effbb0619df4ed`

## Crash / replay 語意

Importer 不會在整批開始前一次把 cursor 推到 journal 尾端；而是每個 event 成功套用後才更新 cursor。

因此：

```text
verify complete source journal
→ compare durable source cursor
→ apply event N
→ atomic cursor=N
→ apply event N+1
→ atomic cursor=N+1
```

若在 event N+1 apply 前 crash，重啟只會從 N+1 繼續。

若 apply 已完成但 cursor 寫入前 crash，N+1 可能被再次送給 projector，所以 projector 自身仍必須具備 idempotent / conflict fail-closed invariant。第十六批 WorkLedgerBridge artifact replay identity gate 正是這一層保護的一部分。

## 明確未完成

本批 **沒有** 宣稱多機 WorkLedger merge 已完成。

尚缺：

1. journal event → WorkLedger / ProjectKnowledge 的正式 deterministic projector；
2. 不同 source host 同一 work/revision 的 merge policy；
3. cross-host revision ownership / migration contract；
4. transport（共享資料夾、Drive、GitHub artifact 或其他 durable exchange）；
5. 三台實機離線→上線→同步→重放 REAL 驗證。

## 目前正確架構

```text
UL7 local WorkLedger + UL7 hash journal
ODA local WorkLedger + ODA hash journal
O87 local WorkLedger + O87 hash journal

replicated source journal
→ full hash-chain verification
→ per-source cursor verification
→ unseen delta only
→ projector（下一批）
→ local authoritative projection
```

SQLite 繼續作為各機本地權威工作狀態／索引；portable append-only journal 是跨機 durable replication contract，不要求某一台永遠在線。

## CI

- importer implementation run #330：執行中。
- importer tests run #331：已建立，等待完整 pytest/gui-unit/gui-e2e terminal。

目前狀態：`IMPLEMENTED — WAITING FOR FULL CI VERIFICATION`。
