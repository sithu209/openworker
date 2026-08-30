# Case 0005 白雪公主：Cluster → ODA 本機總控啟動缺口

日期：2026-08-18

## 目標

Case 0005 固定在 `DESKTOP-ODAQN0D`，工作目錄固定為：

`D:\AI-Work\jobs\0005-SNOW-WHITE`

業務執行必須由 ODA 上常駐的 OpenWorker 本機總控負責，使用最多 4 個本機 worker / agent slot 並行呼叫 go-tool、ComfyX、ComfyX-Studio、OpenMAIC 等 action。GitHub Actions 不得作為業務 scheduler。

## 已有能力

OpenWorker 本機節點已提供：

- `POST /v1/cases/bootstrap`
- 在 durable ACK 前先建立 workspace
- 將 Case controller bootstrap 寫入本機 durable queue
- `GET /v1/jobs` / `GET /v1/jobs/{id}` / progress / supervisor API 查進度

Cluster 層也已提供：

- `POST /v1/cluster/jobs`
- `GET /v1/cluster/jobs`
- machine 精確路由
- durable ACK 與 dispatch ledger

## 缺口

目前缺少 `POST /v1/cluster/cases/bootstrap`。

因此上層總控雖然知道 Case 0005 應固定在 `DESKTOP-ODAQN0D`，卻不能用一個 cluster API 直接把 Case bootstrap 轉發到 ODA 的本機總控，只能退回不必要的 GitHub runner transport。

## 修補方案

新增：

`POST /v1/cluster/cases/bootstrap`

請求沿用本機 case bootstrap contract，至少包含：

- `case_id`
- `machine`
- `workspace_root`
- `openworker_root`
- `controller_module`
- `manifest_path`
- `spec_path`
- optional `python_exe`
- optional `env`

Cluster controller 必須：

1. 依 `machine` 精確選擇 ODA。
2. 轉發到選中節點的 `/v1/cases/bootstrap`。
3. 要求 HTTP 202。
4. 驗證回傳 machine 與選中節點一致。
5. 回傳 selected node + remote durable ACK。
6. 記錄 cluster control / dispatch evidence。

## Case 0005 正確路徑

`ChatGPT / go-tool → OpenWorker cluster API → DESKTOP-ODAQN0D → /v1/cases/bootstrap → Case0005Controller → ODA 本機 durable jobs → 4 worker slots → REAL artifacts → QC / ledger`

## 驗收

只有以下條件同時成立才算 Case 0005 真正啟動：

- cluster bootstrap 選中 `DESKTOP-ODAQN0D`
- ODA 回傳 durable ACK
- `D:\AI-Work\jobs\0005-SNOW-WHITE\.openworker` 已實體建立
- ODA `/v1/jobs` 可查到 `case0005-bootstrap-*`
- 後續工作由 ODA 本機 worker slot 執行
- GitHub Action 不承擔業務執行
