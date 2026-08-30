# OpenWorker 多機持久化第十七批：Hash-Chain Journal 基礎進度

時間：2026-08-17 11:12 +08:00

## 本批目標

在不取代既有 WorkLedger SQLite 的前提下，補上三台機器可各自離線累積、後續搬運與驗證的 append-only journal contract。

## 已完成

新增 `coworker/work_sync_journal.py`。

每一條 journal 僅允許一個 `source_host`，事件包含：

- `source_sequence`
- `previous_hash`
- `event_hash`
- `event_type`
- `work_code`
- `revision_id`
- `payload`

事件 hash 對 canonical JSON 計算 SHA256，形成 per-host hash chain。

驗證規則：

1. source sequence 必須從 1 起連續；
2. previous_hash 必須指向上一事件；
3. event_hash 必須與事件 bytes 的 canonical representation 一致；
4. 同一 journal 不得混入另一 source_host；
5. event hash 不得重複；
6. 任一歷史內容被修改、刪除造成 sequence/hash chain 不一致時 fail-closed。

新增 cursor：

`openworker-work-sync-cursor/v1`

包含 source_host、最後 source_sequence 與 event_hash，供後續 replication/import checkpoint 使用。

## 永久測試

新增 `tests/test_work_sync_journal.py`：

- append + verify + cursor
- 篡改既有歷史 fail-closed
- sequence gap fail-closed

## 與 WorkLedger 的邊界

這個 journal 不是第二套 WorkLedger，也不取代 SQLite。

目前定位：

```text
local WorkLedger / local runtime
        ↓
per-host append-only sync journal
        ↓
transport / replication（下一階段）
        ↓
verified importer / merge policy（下一階段）
        ↓
WorkLedger authority
```

下一批才補 verified importer、per-source cursor 與 duplicate/conflict 規則，避免把 transport、merge、authority 一次混在一起。

## Case 0003

最新 Case 0003 REAL run：`31989592032 / #23`，目前仍 pending，分類仍為 UL7 infrastructure waiting，不是產品 TOOL_GAP。
