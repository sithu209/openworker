# OpenWorker LLM 成果審查第七批：Drive 自動探測與完整成果覆蓋進度

時間：2026-08-17 10:26（Asia/Taipei）

## 本批目標

延續 OpenWorker 的「REAL 成果 → Review Bundle → Google Drive → ChatGPT → PASS / TUNE / TOOL_GAP → WorkLedger」閉環，補兩個實際會阻塞或產生假驗收的缺口：

1. Google Drive Desktop handoff 不應只依賴人工設定 repository variable。
2. ChatGPT 不能只看 Review Bundle 的部分成果就把整個 revision 判定 PASS。

## 已完成 1：Google Drive Desktop bounded 自動探測

`coworker/review_cycle.py` 已新增 `resolve_drive_sync_root()`。

解析順序：

1. `OPENWORKER_REVIEW_DRIVE_ROOT` 明確設定優先；
2. 未設定時，只檢查有限且可預期的 Google Drive Desktop 位置；
3. 支援 `OpenWorker-ChatGPT-Review-TEMP`、`My Drive`、`我的雲端硬碟` 等常見目錄形態；
4. Windows 僅檢查磁碟根目錄下的有限候選，不做全碟 recursive search；
5. 找不到時 fail-closed；
6. 找到多個時 fail-closed，要求明確設定，避免把成果交到錯誤 Google 帳號或錯誤 Drive。

Google Drive 專用臨時 review folder：

- 名稱：`OpenWorker-ChatGPT-Review-TEMP`
- Drive Folder ID：`1A4BnZEcFe2WIhcperRd4QSpxoSUN_ARR`

實作 commit：`58a9ce777e50490d0bfe6160988afb1bafbc931c`

永久測試：`tests/test_review_drive_resolution.py`

測試 commit：`9442e7e2403a761a47f75080dd585d823d13bc99`

## 已完成 2：PASS 必須覆蓋完整 Review Bundle

`coworker/review_gap.py` 已新增 PASS coverage gate。

新的語義：

```text
Review Bundle
  artifact A
  artifact B
  artifact C
        ↓
ChatGPT receipt
        ↓
如果只列 A/B：拒絕 PASS
如果包含未知 artifact：拒絕 PASS
如果重複 artifact：拒絕 PASS
只有 A/B/C 全部覆蓋：才允許 PASS
```

OpenWorker 會從 immutable `review-request.json` 取得每個 artifact 的權威 SHA256，並把 SHA 補入 `llm-review-receipt.json` / WorkLedger check evidence。

因此之後可以回答：

- 大模型當時到底看了哪些成果？
- 接受的是哪一個 SHA256？
- 是否有成果漏看？
- 下一次 revision 的成果 SHA 是否改變？

實作 commit：`8fef199ebc015a128ae8f514eb0a73c60b40d976`

永久測試：`tests/test_review_pass_coverage.py`

測試 commit：`206e829238ba52e49da8c5577e98c0df19fbe4ef`

## Case 0003 目前狀態

Case 0003 workflow 已包含以下 trigger paths：

- `scripts/case0003_review_handoff.py`
- `scripts/case0003_apply_llm_review.py`
- `coworker/review_cycle.py`
- `coworker/review_gap.py`
- WorkLedger / JobBinding 相關檔案

因此 Review governance 的修改會重新派發 Case 0003 REAL validation。

最新 Case 0003 REAL workflow：

- run：`31987851129`
- run number：16
- 狀態：`pending`
- 目前仍未取得 UL7 runner

上一個 run `31987808581` 已由 concurrency 自動 cancelled，符合 single-writer 規則。

## CI 狀態

最新通用 CI：

- run：`31987861736`
- head：`206e829238ba52e49da8c5577e98c0df19fbe4ef`
- 狀態：`in_progress`

目前不可提前宣告 CI PASS。

## 現在的權威閉環

```text
REAL artifact production
→ OpenWorker mechanical reopen/check
→ immutable Review Bundle + SHA256
→ bounded Google Drive Desktop handoff
→ WAITING_LLM_REVIEW
→ ChatGPT 必須查看完整 bundle
→ PASS / TUNE / TOOL_GAP

PASS
→ 全 artifact coverage + authoritative SHA
→ LLM Semantic Review passed
→ accept_revision
→ deliver_revision

TUNE
→ allowlisted parameter delta
→ before / after / reason / expected effect
→ child revision
→ REAL rerun
→ 新 Review Bundle
→ ChatGPT compare

TOOL_GAP
→ gap_capability / gap_description / owning_repo / verification_plan
→ REWORK_REQUIRED
→ 修 owning repo
→ permanent test
→ child revision
→ REAL rerun
→ 新 Review Bundle
→ ChatGPT re-review
```

## 尚未完成

1. UL7 runner 尚未接下 Case 0003 最新 REAL run，因此還沒有第一份真實 Review Bundle 上傳到 Drive。
2. Drive Desktop 實機路徑尚未被 UL7 REAL run 驗證。
3. 尚未由 ChatGPT 對第一份 Case 0003 Review Bundle 產生正式 receipt。
4. 尚未完成第一個 PASS / TUNE / TOOL_GAP 的實際 WorkLedger 後續鏈。

在上述 REAL 證據出現前，Case 0003 的新 LLM review gate 狀態維持 `VERIFYING / WAITING FOR UL7 REAL HANDOFF`，不得標記 CLOSED。
