# Case 0005：Go Case Engine Terminal Reconciliation 實作進度

更新時間：2026-08-19 14:04 +08:00

## 1. 現況

Case 0005 已成功由 Go-native Case Engine 提交第一個 durable business work：

- step：`0005-010`
- capability：`comfyx-studio.director.preproduction`
- work_id：`case0005-0005-010-r000014-17b8b780`
- revision：`14`
- authority：`go-tool-runtime :8848 durable local-work`

目前仍禁止重提新的 `0005-010`。原 work_id 保持不變，SQLite durable queue 不 clear。

ODA 已於 go-tool deployment run `32218984221` REAL 安裝 claim-slot 自癒版本：

- source commit：`55e0204ec1f5762c2e664feb166fd5fc175cf4f1`
- deployment receipt commit：`a4ead02dda92a3924d82ec042c68fee048175535`
- REAL four-slot verifier：success
- GitHub Action business execution：false

## 2. Terminal reconciliation 已 SOURCE IMPLEMENTED

OpenWorker commit：`52b8e70ece18823e9c01fed523d5ef539c288b97`

`go-runtime/internal/casecontroller/continue.go` 已新增：

- current durable work 優先 reconciliation；
- `pending / claimed / running` 不重提；
- `completed` 驗證 acceptance 後 atomic 寫回 worklist；
- `failed` 寫 `FAILED + blocker`，fail-closed；
- completed ledger：`go_step_reconciled_completed`；
- failed ledger：`go_step_reconciled_failed`。

## 3. 0005-020 mapping 已實作

Commit：`52b8e70ece18823e9c01fed523d5ef539c288b97`

- capability：`comfyx-studio.storyboard.plan`
- parent：`0005-010 = SUCCEEDED`
- Director plan 必須是真實 workspace 內檔案
- absolute canonical path 轉 bounded relative path 後才傳給 leaf capability

## 4. 0005-025 text-only PPTX mapping 已實作

OpenWorker commit：`181b1ad0ebd047ed123f21e456512f8e50e7b149`

- capability：`presentation.openmaic`
- parent：`0005-020 = SUCCEEDED`
- input：`0005-020.storyboard_request`
- request 必須位於 workspace 內且真實存在
- 固定 output：`presentation/storyboard-text-only.pptx`

回歸測試 commit：`fcc3e143e62e0a84752726bd23817d2589a921d3`

## 5. OpenMAIC evidence contract 已對齊 Case acceptance

go-tool-runtime commit：`1978e685be07e3813fa4c4c0b50589b09b2ab8bc`

除通用 evidence 外，正式提供：

- `storyboard_pptx`
- `storyboard_manifest`
- `storyboard_pptx_sha256`
- `image_count`
- `reopen_receipt`

因此 `0005-025` 可以由 Go reconciliation 正式驗收，不需要 Case-specific Python 轉換。

## 6. 0005-026 text-only storyboard → Google Drive mapping 已 SOURCE IMPLEMENTED

OpenWorker commit：`25aef4642364374b2a6c8e446d54ef99cecefd64`

Go Case Engine 已加入：

- step：`0005-026`
- capability：`openworker.case.publish-artifacts`
- parent：必須 `0005-025 = SUCCEEDED`
- artifact inputs：`storyboard_pptx`、`storyboard_manifest`、`reopen_receipt`
- 每個 artifact 都必須是真實 workspace 內檔案；轉 bounded relative path 後才交給 publisher
- deterministic revision identity：`case0005-text-storyboard-r000014`
- deterministic work code：`CASE0005-TEXT-STORYBOARD-R000014`
- GitHub Action 不作 artifact transport
- publication 必須 ODA 本機經 Google Drive API 完成

### Drive publisher evidence alias 修復

go-tool-runtime commit：`ec8fbaa7ca053b768a20ad8add18d8b994a8261e`

正式補齊：

- `published_artifact_sha256`
- `drive_file_ids`
- `drive_file_links`

保留既有 `published_artifacts` / `drive_files` 結構化 evidence，不再由 Case controller 猜測。

## 7. 0005-027 text-only storyboard approval gate 已 SOURCE IMPLEMENTED

OpenWorker commit：`6166f18c4f798425778d654a96d2bf5b086a1e36`

Go Case Engine 已加入：

- step：`0005-027`
- capability：`openworker.review.await-drive`
- parent：必須 `0005-026 = SUCCEEDED`
- publish evidence 必須至少有 `drive_folder_id` + `manifest_sha256`
- fixed evidence path：`evidence/0005-027-drive-gate.json`
- bounded timeout：43200 秒
- deterministic work_id 繼續由 case + step + capability + revision 生成

Leaf gate contract 已確認：

- 只接受固定 `step_id=0005-027`
- 只等待精確 Drive receipt：`case0005-0005-027-receipt.json`
- receipt schema：`openworker-case0005-drive-gate-receipt/v1`
- receipt 不得含 command / commands / tool 欄位
- reviewed_files 必須與本機 0005-026 publish evidence 的 path/SHA/Drive ID 完全一致
- decision 只允許 `APPROVE` 或 `REJECT`
- `REJECT` → fail-closed，後續插圖生成保持 blocked
- `APPROVE` → evidence：
  - `approved_storyboard_pptx_sha256`
  - `approval_decision=APPROVE`
  - `approval_receipt`

因此「先產生無配圖 storyboard PPTX → 使用者 / ChatGPT 確認 → 才開始插圖」已正式進入 Go Case 主控流程。

注意：`openworker.review.await-drive` 目前 leaf capability 仍以 Python script 實作 Drive polling / receipt validation；這符合目前架構原則：**Python 只留 leaf tool，不參與 Case orchestration / queue / state machine**。

## 8. ODA claim runtime 自癒已 REAL 部署

修復 commit：`55e0204ec1f5762c2e664feb166fd5fc175cf4f1`

- slot error 不殺整個 agent
- individual slot 自動重啟
- backoff：1 → 2 → 4 → 5 秒
- `--once` 仍 fail-fast

ODA deployment run：`32218984221`，REAL four-slot verifier success。

## 9. Current durable work 可觀測性正在收斂到 resident-node authority

resident-node workflow 已直接增加：

- exact `.openworker/case-controller-last.json` work_id 讀取
- `GET :8848/api/execution/local-work/<work_id>`
- `GET :8848/api/execution/local-work/<work_id>/events`
- local supervisor status
- immutable receipt：`case-evidence/case0005-current-work/latest.json`

workflow commit：`dff9159f9c16cfe94597747952b956bd1a3693a8`

最新 full-Go validation trigger：`e63378d8f712e13a1cfa6261c8de8c8ed319b22d`

這條 workflow 在 publish current-work receipt 前會先：

- `go test ./...`
- build resident Go node
- install / upgrade service
- verify running commit / target commit
- verify `/v1/cases/continue` 非 404
- publish immutable resident-node receipt

目前 `case-evidence/case0005-current-work/latest.json` 尚未出現，因此仍不得宣稱 `0005-010` terminal。

## 10. 目前 Go-native Case 0005 主鏈

SOURCE contract 已接到：

`0005-010 Director`
→ `0005-020 storyboard request + visual requirements`
→ `0005-025 text-only storyboard PPTX`
→ `0005-026 Google Drive review publish`
→ `0005-027 bounded APPROVE / REJECT gate`

全程：

- Python Case controller = false
- durable queue = `:8848`
- deterministic work_id
- workspace path safety
- acceptance fail-closed
- Google Drive artifact transport only at leaf publisher
- APPROVE 前禁止進入 image generation

## 11. 下一個合法動作

1. 讀回 `case0005-0005-010-r000014-17b8b780` exact durable status。
2. 若 pending：只修 claim/runtime，不重提。
3. 若 claimed/running：只追 status。
4. 若 failed：修 Director leaf capability。
5. 若 completed：Go reconciliation 驗收六項 evidence，立即進 `0005-020`。
6. 020 completed → 0005-025 text-only PPTX。
7. 025 completed → 0005-026 ODA → Google Drive publish。
8. 026 completed → 0005-027 等待 APPROVE；APPROVE 前不生成任何插圖。
