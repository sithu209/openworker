# OpenWorker Google Drive 成果發布與 ChatGPT 品質審查缺口

> **2026-08-20 CURRENT CONTRACT OVERRIDE — HISTORICAL EVIDENCE ONLY**
>
> 本文件以下內容保留為 2026-08-17 的歷史設計、失敗教訓與 REAL 演進證據。**不得再把 OpenWorker、WorkLedger、Drive Desktop 或本文件內的舊 publish implementation 當成現行操作 authority。**
>
> 現行做法：先問 go-tool；business execution 由 DirectWork 建 durable work；普通成果給 ChatGPT 審查使用 `drive.chatgpt.review.publish`，其 canonical primitive 為 `drive.file.publish-verified`。完成必須包含 Google Drive upload、independent remote verification、exact Drive revision/file identity，再由 ChatGPT 審查該 exact revision。
>
> 本文件中「Drive Desktop copy 不能證明雲端 publication」以及「需要 cloud identity / SHA / idempotency / exact revision」等教訓仍然有效；已被吸收到現行 verified Drive capability contract。

- 日期：2026-08-17 13:24（Asia/Taipei）
- Repo：`liuxb99/openworker`
- 狀態：HISTORICAL DESIGN / SUPERSEDED OPERATION
- 優先級：歷史 P0 / P1 缺口；現行替代路徑已由 go-tool + DirectWork contract 接管

## 1. 結論

OpenWorker 並不是完全沒有 Google Drive 審查能力。現有 `ReviewCycle` 已能建立不可變 review bundle、計算 SHA256，Case 0003 也已能把 bundle 複製到 Google Drive Desktop 的本機同步資料夾，之後等待 ChatGPT LLM Review receipt。

真正缺口是：**「複製到本機 Google Drive 同步目錄」不能等同於「OpenWorker 已經把這個 revision 的成果正式發布到 Google Drive 雲端，且 ChatGPT 能精確定位同一批成果」。**

目前同步路徑缺少雲端 `file_id`、`webViewLink`、revision cloud folder identity、正式 publish receipt，以及 cloud identity → WorkLedger revision 的可追蹤綁定。因此，即使本機 copy 與 SHA 驗證成功，也只能證明「已交給 Desktop sync」，不能證明「雲端已發布並可供 ChatGPT 精確審查」。

## 2. 現況

現有閉環已經有以下能力：

1. `ReviewCycle.build_bundle()` 會把待審查成果複製到 `.openworker/reviews/<revision_id>/`。
2. `review-request.json` 已記錄 revision、review dimensions、能力 owner、參數 allowlist、artifact SHA256/size。
3. `manifest.json` 已形成 review bundle manifest。
4. `handoff_to_drive_sync()` 會把 bundle 原子複製到 Google Drive Desktop sync root，並逐檔驗證 SHA256。
5. LLM review receipt 已能回寫 WorkLedger；PASS / TUNE / FAIL 已有治理邏輯。
6. Case 0003 已有 `WAITING_DRIVE_HANDOFF` / `WAITING_LLM_REVIEW` gate，LLM review 前不得 accept/deliver。

這些設計保留，不重做。

## 3. 真正缺口

### G1 — Desktop sync handoff 沒有雲端完成證明

本機 `target.exists()` 與本機 SHA 一致，只能證明 Desktop sync 目錄收到檔案，不能證明 Google Drive server 已收到檔案。

### G2 — 沒有 Drive cloud identity

目前 `drive_folder_id` 主要是 metadata；每一個成果沒有：

- `drive_file_id`
- `webViewLink`
- revision 專屬 Drive folder ID
- cloud folder URL

ChatGPT 因此無法靠正式 receipt 精確鎖定「這一次 revision」的成果。

### G3 — 沒有正式 publish receipt

缺少一份 machine-readable receipt，證明：

`local artifact SHA → Drive cloud file ID → revision → machine → case/job/run`

### G4 — 雲端發布結果尚未成為 WorkLedger evidence

WorkLedger 是 durable authority；Google Drive 只是 review transport。正確做法不是讓 Drive 取代 WorkLedger，而是把 cloud publication receipt 登錄回 WorkLedger。

### G5 — 中斷重試需要 fail-closed / idempotent

如果上傳到一半斷線，重跑時不得靜默覆寫同名但不同 SHA 的檔案。相同 revision + 相同相對路徑若雲端已存在：

- SHA 相同：允許 reuse，繼續完成剩餘發布。
- SHA 不同：立即 fail closed，要求開新 revision 或人工處理。

## 4. 目標架構

> **歷史架構，已 superseded。** 現行請使用文件頂部 CURRENT CONTRACT OVERRIDE。

正式鏈路定義為：

```text
Fixed Machine / OpenWorker Service
        |
        v
Local Workspace REAL Artifact
        |
        v
Mechanical / Artifact QC
        |
        v
Immutable Review Bundle + Manifest SHA
        |
        v
Google Drive API Publication
        |
        +--> Work Folder
        |      +--> Revision Folder
        |             +--> artifacts/*
        |             +--> manifest.json
        |             +--> review-request.json
        |             +--> review-publish-receipt.json  (最後上傳)
        |
        v
Cloud IDs + Web View Links + SHA Receipt
        |
        v
WorkLedger Evidence
        |
        v
WAITING_LLM_REVIEW
        |
        v
ChatGPT reads exact Drive revision
        |
        +--> PASS -> ACCEPTED / DELIVERED
        +--> TUNE -> child tuning revision -> rerun
        +--> FAIL -> REWORK_REQUIRED -> owning repo
```

## 5. 正式 Review Publish Contract

> **以下 schema 為歷史 OpenWorker contract，保留作 migration/provenance 參考；不是現行 capability ID。**

`review-publish-receipt.json` schema：`openworker-review-publish-receipt/v1`

必要欄位：

```json
{
  "schema_version": "openworker-review-publish-receipt/v1",
  "transport": "google-drive-api",
  "status": "WAITING_LLM_REVIEW",
  "revision_id": "...",
  "work_code": "...",
  "machine_id": "...",
  "drive_root_folder_id": "...",
  "drive_revision_folder_id": "...",
  "drive_revision_web_view_link": "...",
  "bundle_manifest_sha256": "...",
  "published_at": "...",
  "files": [
    {
      "relative_path": "artifacts/render.png",
      "sha256": "...",
      "size_bytes": 123,
      "mime_type": "image/png",
      "drive_file_id": "...",
      "web_view_link": "..."
    }
  ],
  "metadata": {
    "case_id": "...",
    "job_id": "...",
    "run_id": "..."
  }
}
```

`metadata` 允許案例補充 provenance，但 secret/token 不得寫入。

## 6. Drive API Transport 規則

### 6.1 認證

不得把 API key、OAuth refresh token、access token 寫進 repo、workspace artifact、review receipt 或 WorkLedger。

正式程式支援：

1. `OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN`：短期/診斷用途。
2. Google Application Default Credentials：正式服務優先。
3. `OPENWORKER_GOOGLE_DRIVE_SCOPE` 可顯式設定 scope；預設使用可操作專用 review folder 的 Drive scope。

> 上述環境變數/認證方式是歷史 OpenWorker 實作細節。現行大模型不得自行依此重建 uploader 或 OAuth 流程；先問 go-tool 使用 verified Drive capability。

### 6.2 大檔案

成果可能是 MP4 / GLB / PDF，因此不可把 512 MB bundle 全部讀進記憶體。Drive transport 使用 resumable upload，檔案以 stream 傳輸。

### 6.3 冪等性

每個雲端檔案帶 `appProperties.openworkerSha256`。重試時：

- 同名 + SHA 相同：reuse。
- 同名 + SHA 不同：fail closed。
- 同名多筆造成 ambiguity：fail closed。

### 6.4 Receipt 最後上傳

`review-publish-receipt.json` 必須最後才寫入並上傳。它代表前面的 bundle files 已經取得 cloud identity；不能先產 receipt 再假設上傳一定成功。

## 7. Google Drive Desktop Sync 的定位

既有 `handoff_to_drive_sync()` 暫時保留，避免現有案例與既有機器立即中斷。

但正式語意改為：

- `google-drive-sync` = compatibility / transitional transport。
- `google-drive-api` = cloud-identity-complete production transport。

只有 API publish receipt 能證明 OpenWorker 已取得雲端 file/folder identity。

> **2026-08-20 更正**：Drive Desktop sync 現在只允許當歷史/compatibility evidence；普通成果審查的現行 publication authority 是 `drive.chatgpt.review.publish -> drive.file.publish-verified` 的 remote verification 結果。

## 8. WorkLedger 規則

Google Drive 不是 durable authority。正式 durable evidence 仍在 WorkLedger。

成功發布後必須記錄：

- `review-publish-receipt.json` artifact
- transport = `google-drive-api`
- revision Drive folder ID
- revision Drive URL
- manifest SHA
- machine ID
- case/job/run provenance（若有）

然後 revision 只能進入 `WAITING_LLM_REVIEW` / blocked，而不能直接 accepted/delivered。

LLM receipt 是唯一允許進入 PASS/TUNE/FAIL 後續治理的入口。

> **2026-08-20 更正**：上段是歷史資料治理模型。現行 business completion authority 是 DirectWork durable work/evidence；既有 WorkLedger/receipt 可保留為 provenance evidence，但不得凌駕 DirectWork current contract。

## 9. 本批實作

本批新增 `coworker/review_drive.py`：

- `DrivePublishedFile`
- `ReviewPublishReceipt`
- `ReviewDriveUploader` protocol
- `GoogleDriveAPIClient`
- ADC / env access token auth
- Drive v3 folder discovery/create
- resumable file upload
- SHA idempotency / immutable conflict gate
- recursive bundle directory preservation
- per-file Drive ID / URL
- revision Drive folder ID / URL
- `review-publish-receipt.json`
- receipt 最後上傳

並新增永久測試 `tests/test_review_drive_publish.py`，用 fake uploader 驗證 contract，不依賴真實網路或真實 Drive credential。

## 10. 驗收標準

### Code gate

- [ ] 新 transport 可 import / compile。
- [ ] fake Drive 測試證明每個 bundle file 都取得 cloud identity。
- [ ] nested `artifacts/` 在 Drive 保留資料夾階層。
- [ ] publish receipt 不把自己列進 files，且最後上傳。
- [ ] 缺 manifest / machine identity 時 fail closed。
- [ ] 無 credential 時 fail closed，而不是退化成「假成功」。

### REAL gate

- [ ] 在固定 worker 上設定正式 Drive credential。
- [ ] 對一個真實 review bundle 執行 `google-drive-api` publication。
- [ ] Drive revision folder 可由 ChatGPT connector 直接找到。
- [ ] 隨機抽一個成果，local SHA 與 publish receipt SHA 一致。
- [ ] receipt 內 file ID 可直接定位同一個 cloud file。
- [ ] publish receipt 回寫 WorkLedger。
- [ ] revision 進入 `WAITING_LLM_REVIEW`，未收到 LLM receipt 前不得 accepted/delivered。

## 11. 完成定義

這個缺口不能以「本機 Google Drive 資料夾已經出現檔案」判定 DONE。

只有以下四件事同時成立，才能標記 CLOSED：

1. OpenWorker 取得真實 Google Drive cloud file/folder IDs。
2. 有 `openworker-review-publish-receipt/v1` 串起 local SHA 與 cloud identity。
3. publish receipt 進入 WorkLedger durable evidence。
4. ChatGPT 對真實 Drive revision 完成一次 review，review receipt 回到 WorkLedger 並驅動 PASS/TUNE/FAIL。

> **2026-08-20 CURRENT completion 定義**：不要再以 OpenWorker receipt/WorkLedger 作唯一完成條件。現行要求為 DirectWork durable work completed + REAL artifact + Drive upload + independent remote verification + exact Drive revision identity + ChatGPT review receipt（需要審查時）。

在 REAL gate 完成前，代碼狀態只能是 **IMPLEMENTED — WAITING FOR REAL DRIVE VERIFICATION**，不能寫成完全閉環。
