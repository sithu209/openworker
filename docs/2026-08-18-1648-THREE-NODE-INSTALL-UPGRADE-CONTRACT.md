# OpenWorker 三節點安裝／升級／版本自證閉環

時間：2026-08-18 16:48（Asia/Taipei）

## 目的

OpenWorker 的三台固定工作電腦必須全部安裝 `OpenWorkerNode`，並使用同一套可重複升級、可觀測、fail-closed 的版本自證規則。不能再只對 ODA 做特例，也不能以 Git push/trigger 當作升級成功。

固定節點：

- UL7：`DESKTOP-UL7V2VV`，runner label `UL7`
- O87：`DESKTOP-O87PJNR`，runner label `O87`
- ODA：`DESKTOP-ODAQN0D`，runner label `ODA`

## 統一安裝／升級 contract

三個 node bootstrap workflow 都支援：

1. `workflow_dispatch` 手動安裝或升級。
2. main branch push commit message 含 `[upgrade-openworker-nodes]` 時，同時觸發三台固定節點。
3. 各 workflow 仍保留自己的單機 bootstrap marker。
4. `runs-on` 固定到自己的 runner label，並再次以 `COMPUTERNAME` fail-closed 驗證實體電腦。
5. 編譯時把同一個 `GITHUB_SHA` 注入：
   - `buildinfo.Commit`
   - `buildinfo.TargetCommit`
6. 停止舊 `OpenWorkerNode`、覆蓋 binary、重新建立或更新 Windows Service、啟動服務。
7. 服務必須通過 `/healthz`。
8. 服務必須通過 `/v1/node/status` 權威版本自證。

## 升級成功的唯一判定

每台節點只有同時符合以下條件才是 `VERIFIED`：

- Windows Service = `Running`
- `machine` 等於該 workflow 固定的實體電腦名稱
- `build.commit == GITHUB_SHA`
- `service.running_commit == GITHUB_SHA`
- `service.target_commit == GITHUB_SHA`
- `service.upgrade_verified == true`
- `service.upgrade_status == VERIFIED`
- `lease_until` 存在
- 該機必要 capability 存在
- `advertise_endpoint` 存在

任何一項不成立，workflow 必須失敗，OpenWorker 不得顯示「升級成功」。

## 三台能力分工維持不變

UL7 保留工程橋梁能力，例如 `case0003, bridge, blender, scenex, engineering, drive-review`。

O87 保留工程 DWG/案例能力，例如 `case0004, dwg, story-index, engineering`。

ODA 保留 ComfyX/影片/簡報與 local supervisor 能力，例如 `case0002, case0005, comfyx, minimax-h3, video, storyboard, presentation, local-supervisor`。

這些是 capability routing；安裝／升級／版本自證則三台完全共用同一 contract。

## 中央 OpenWorker 的責任

中央 cluster controller 應以節點 heartbeat/probe 回傳的實際 `service` 狀態作為權威，不再以 GitHub Actions trigger 代替 runtime truth。

因此未來查詢三台狀態時，應能直接得到類似：

```text
UL7  ONLINE  VERIFIED  running=<sha> target=<sha>
O87  ONLINE  VERIFIED  running=<sha> target=<sha>
ODA  ONLINE  VERIFIED  running=<sha> target=<sha>
```

若某台離線、尚未安裝、版本不一致或升級失敗，必須清楚顯示 `OFFLINE`、`UNTRACKED`、`MISMATCH` 或相應錯誤，而不是推測成功。

## 本批完成內容

- UL7 bootstrap workflow 接入共用 `[upgrade-openworker-nodes]` marker。
- O87 bootstrap workflow 接入共用 `[upgrade-openworker-nodes]` marker。
- ODA bootstrap workflow 接入共用 `[upgrade-openworker-nodes]` marker。
- UL7/O87 補齊 `TargetCommit` build injection。
- UL7/O87 補齊 authoritative `service.running_commit/target_commit/upgrade_verified/upgrade_status` 驗證。
- 三台 push 安裝時都會 fallback 到 `127.0.0.1:8787`，避免 `workflow_dispatch` inputs 在 push event 為空造成 listen 缺失。

## 下一步驗收

推送一個含 `[upgrade-openworker-nodes]` 的 commit，讓 UL7、O87、ODA 三個固定 runner 各自接單、安裝／升級。只有三台都從自己本機 `/v1/node/status` 回報 `VERIFIED`，這一批才算真正閉環。
