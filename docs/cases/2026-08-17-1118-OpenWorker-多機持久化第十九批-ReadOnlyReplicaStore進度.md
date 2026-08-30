# OpenWorker 多機持久化第十九批：Read-Only Replica Store 進度

時間：2026-08-17 11:18 +08:00

## 本批目的

在 hash-chained journal + verified importer + per-source cursor 之上，建立可查詢的跨機 replica index，但不直接修改 owner host 的 authoritative WorkLedger。

原因：OpenWorker 目前的 JobBinding 明確把 job 固定到 assigned host。遠端 journal 是可驗證的 replication evidence，不應在沒有 migration/ownership contract 時直接取得 WorkLedger 寫權。

## 已完成

### `coworker/work_sync_replica.py`

新增 `WorkSyncReplicaStore`：

- SQLite-backed read-only replica event materialization。
- primary key：`(source_host, source_sequence)`。
- `event_hash` 全域 unique。
- 保存 `previous_hash / event_type / work_code / revision_id / payload`。
- exact same event 再 project：idempotent。
- 同 source/sequence 但任何 identity/content 不同：`REPLICA_EVENT_CONFLICT`，fail-closed。
- 可依 source host / work code 查詢。
- `source_heads()` 可看每個來源目前已 materialize 到哪一筆。

實作 commit：`5027966860dddf3463fedac7e3b7435fe7609f57`

### 永久測試

新增 `tests/test_work_sync_replica.py`：

1. `WorkSyncImporter` 驗證 journal 後，直接 `apply_event=replica.project`，兩筆事件進 replica；再次 import 為 0 筆。
2. exact same source/sequence/event 可 idempotent project。
3. 同 source/sequence 但 payload 改變，即使呼叫者誤傳，也必須 `REPLICA_EVENT_CONFLICT`。
4. UL7 / ODA source heads 各自獨立，不互相覆蓋。

測試 commit：`b47919947a9c74d18d90b93efa548b8dca3c99e0`

## Authority 邊界

目前正確分層：

```text
owner host
  WorkLedger SQLite  ← authoritative mutation
  local hash journal

other host
  replicated journal
  → hash-chain verification
  → per-source cursor
  → read-only replica SQLite
```

`WorkSyncReplicaStore` 不提供 accept/deliver/rework/head movement，也不改 JobBinding。

這避免「ODA 看到 UL7 的事件就直接改 UL7 job 的權威 ledger」這種 split-brain。

## 下一個缺口

下一批應補 deterministic global view / merge policy：

- 同一 work_code 在不同 source host 的事件如何聚合；
- owner host 身分如何寫入 global view；
- 非 owner event 只能作為 observation/replica，不能升格成 authority；
- explicit migration 後 owner epoch 如何切換；
- 防止舊 owner 離線後重新上線把過期歷史重新當 authority。

在 owner epoch / migration contract 完成前，不應做 automatic cross-host WorkLedger merge。

## CI

Importer CI #331：gui-unit 已 SUCCESS；pytest 與 gui-e2e 執行中。
Replica commits 已觸發後續 CI，等待 terminal。

狀態：`IMPLEMENTED — WAITING FOR FULL CI VERIFICATION`。
