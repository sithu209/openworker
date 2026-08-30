# OpenWorker LLM 成果審查／參數調整／返工閉環缺口

日期：2026-08-17
狀態：IMPLEMENTING

## 1. 缺口

目前 OpenWorker 已有 WorkLedger、REAL Final Acceptance、artifact SHA、required checks、REWORK_REQUIRED 與 child revision，但仍缺少一個關鍵的人機／模型品質閉環：

1. Action 產生的成果主要留在本機 workspace / GitHub Actions artifact。
2. ChatGPT 無法穩定直接看到每台 self-hosted runner 的本機成果。
3. 機械式驗收（檔案存在、SQLite quick_check、Blender reopen、SceneX diagnostics）通過，不代表視覺與語義品質已經達標。
4. 大模型看完成果後，常會需要調整工具參數，而目前參數調整原因、前後值、預期效果、實際效果沒有形成正式 revision history。
5. 若調參後成果更差，也需要能回到前一個 accepted candidate，而不是覆蓋歷史。

## 2. 目標閉環

```text
REAL execution
  -> physical/mechanical verification
  -> bounded Review Bundle
  -> Google Drive temporary review exchange
  -> ChatGPT visual/semantic review
       PASS -> review receipt -> acceptance gate
       TUNE -> parameter proposal -> child revision -> rerun -> compare -> review again
       FAIL -> REWORK_REQUIRED -> owning repo repair -> child revision -> rerun
```

Google Drive 僅是 Review Exchange，不是權威資料庫。權威歷史仍由 WorkLedger 保存。

目前已建立 Google Drive 臨時資料夾：

- name: `OpenWorker-ChatGPT-Review-TEMP`
- folder id: `1A4BnZEcFe2WIhcperRd4QSpxoSUN_ARR`

## 3. Review Bundle 最小契約

每次需要模型終驗的 revision 必須產生獨立 bundle：

- `review-request.json`
- `manifest.json`
- 可視成果：PNG/JPG/MP4/PDF/HTML 等
- 必要機械驗收 evidence
- 當前工具參數 snapshot
- 上一 revision 的比較參考（若為 tune/rework）

`review-request.json` 至少記錄：

- work_id / work_code
- revision_id / parent_revision_id
- case/job/project id
- artifact logical names + SHA256
- review dimensions（例如 geometry、visual quality、continuity、readability）
- current_parameters
- previous_parameters
- allowed_parameter_keys
- owning capability / owning repo
- Google Drive review folder id

## 4. LLM Review Receipt

ChatGPT 看完成果後，不能只輸出自然語言，必須落成結構化 receipt：

- verdict: `PASS | TUNE | FAIL`
- summary
- observations[]
- score / dimensions
- parameter_changes[]
  - capability_id
  - parameter
  - before
  - after
  - reason
  - expected_effect
- owning_repo（FAIL 時）
- verification_plan[]
- reviewed_artifacts[] + SHA256
- reviewer/model provenance
- review timestamp

## 5. 調參不是覆寫，是 revision

只要 verdict = `TUNE`：

1. 當前 revision 保留 review receipt。
2. 建立 child revision，kind=`tuning`。
3. child revision 記錄完整 parameter delta。
4. 僅允許 allowlist 中的參數調整；禁止大模型任意改命令、路徑、repo、可執行檔。
5. 重新執行 owning capability。
6. 新成果以新 SHA 記錄。
7. 再上傳新的 Review Bundle。
8. ChatGPT 必須比較 parent / child 的成果，不能只看 child。
9. 若變差，可 checkout 前一 accepted/candidate revision，但不得刪除 tuning revision。

## 6. FAIL 與 TUNE 的區別

- `TUNE`：工具能力本身正確，只需要在已知安全參數範圍內調整，例：camera、sampling steps、CFG、seed policy、LOD、viewport、light intensity。
- `FAIL`：能力/契約/工具有缺口，必須 `REWORK_REQUIRED`，找 owning repo 修工具，不得用案例特例參數逃避。

## 7. WorkLedger 要新增的治理語義

P0：

- revision kind `tuning`
- review receipt
- parameter delta event
- reviewed artifact SHA 綁定
- TUNE -> child revision
- FAIL -> REWORK_REQUIRED
- PASS 才能進 acceptance gate

P1：

- Review Bundle builder
- Google Drive temporary handoff manifest
- review receipt importer
- parameter allowlist / typed validation

P2：

- Action 將 bundle 複製到 Google Drive temporary folder
- ChatGPT 透過 Google Drive connector 實際讀圖/影片/PDF/HTML
- receipt 回寫 WorkLedger
- 自動重跑 parameter-tuning revision
- 清理過期 temporary bundles，但保留 manifest/receipt/SHA provenance

## 8. Case 0003 首個實案

玉井橋將作為第一個 REAL 驗證：

- SceneX 1280x720 screenshot
- Blender render
- delivery HTML
- terrain metadata/evidence

機械 gate 通過後仍需 ChatGPT Review。若模型認為視角、尺度、構圖、terrain presentation 可改善，應走 `TUNE`，調整 allowlisted SceneX/Blender consumer parameters，產生 child revision 再重跑；不是直接改檔案或覆蓋成果。

## 9. 驗收標準

本缺口不能因「有 Google Drive 檔案」就算完成。真正完成必須證明：

`artifact -> Drive handoff -> ChatGPT review receipt -> parameter delta/rework -> child revision -> rerun -> comparison -> accepted revision`

整條 provenance 可由 OpenWorker 查詢，且任一歷史 revision 都不能被覆蓋。
