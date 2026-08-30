# OpenWorker 節點升級成功回執與版本狀態

時間：2026-08-18 16:40 Asia/Taipei

## 問題

過去 ODA、UL7、O87 的升級流程可以看到 Git trigger 或 workflow 被觸發，但中央 OpenWorker 無法只靠這些證據判定遠端服務是否真的已切換到新版 binary。這會造成「已要求升級」與「節點已成功運行新版」混在一起。

## 新權威判定

節點 `/v1/node/status` 現在必須回報 `service`：

- `running_commit`：目前實際運行的 OpenWorkerNode binary commit。
- `target_commit`：本次服務應運行的目標 commit。
- `upgrade_status`：`UNTRACKED`、`PENDING`、`MISMATCH`、`VERIFIED`。
- `upgrade_verified`：只有 `running_commit == target_commit` 時才為 `true`。
- `service_started_at`：目前服務程序啟動時間。
- `supervisor_api_version`：本機 supervisor contract 版本。

中央 cluster registry 直接保存節點 heartbeat 帶回的 `service`，因此 `/v1/cluster/status` 可同時看到每台電腦目前是否在線、工作槽狀態，以及是否真正完成版本升級。

## Fail-closed 規則

1. Git commit / trigger 只能表示「要求升級」，不能表示成功。
2. workflow 成功 build 不能表示服務已切換。
3. Windows Service 顯示 Running 也不能表示版本正確。
4. 只有新服務啟動後，`/v1/node/status` 同時滿足：
   - `build.commit == expected commit`
   - `service.running_commit == expected commit`
   - `service.target_commit == expected commit`
   - `service.upgrade_status == VERIFIED`
   - `service.upgrade_verified == true`
   才能宣告升級成功。
5. ODA Case 0005 bootstrap receipt 已升級為 v2；沒有 verified service upgrade 不允許寫成功回執。

## ODA 實作

ODA workflow 在編譯 binary 時，同時以 Go ldflags 寫入 `Commit` 與 `TargetCommit`。因此 target commit 跟 binary 一起固化，不依賴 Windows Service 額外持久化環境變數。

升級後 workflow 會重新查詢 `http://127.0.0.1:8787/v1/node/status`，只有權威版本欄位全部一致才通過。

## 後續

UL7、O87 應沿用完全相同 contract。中央 UI / ChatGPT / 本機 coder 後續只能根據 cluster registry 的 `service.upgrade_verified` 判定節點是否升級成功，不再從 Git trigger 推測。
