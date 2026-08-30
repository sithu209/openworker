# OpenWorker LLM 成果審查第八批：CI 收斂與 Drive 完整性進度

時間：2026-08-17 10:30（Asia/Taipei）

## 目前狀態

本批持續收斂 OpenWorker 的成果審查治理層，目標不是把 mechanical PASS 當作完成，而是確保：

`REAL 執行 → mechanical reopen → Review Bundle → Google Drive → ChatGPT 完整成果審查 → PASS / TUNE / TOOL_GAP → WorkLedger`。

目前 Case 0003 玉井橋 REAL workflow 仍等待 UL7 runner 接單，因此尚未產生第一份真正的 Google Drive Review Bundle，也尚未進入 ChatGPT REAL 成果審查。

## 本批新增能力

### 1. Google Drive Desktop 同步根目錄有限自動探測

`coworker/review_cycle.py` 已加入 bounded resolver：

1. 優先使用 `OPENWORKER_REVIEW_DRIVE_ROOT`。
2. 未設定時只探測有限、可預期的 Google Drive Desktop 常見同步目錄。
3. 只接受唯一候選。
4. 多個候選時 fail-closed，避免成果被送到錯帳號或錯 Drive。
5. 不做全磁碟遞迴搜尋。

實作 commit：`58a9ce777e50490d0bfe6160988afb1bafbc931c`

永久測試 commit：`9442e7e2403a761a47f75080dd585d823d13bc99`

### 2. ChatGPT PASS 必須完整覆蓋 Review Bundle

Case 0003 receipt apply 現在不允許 ChatGPT 只看部分成果就接受整個 revision。

PASS receipt 必須完整覆蓋 `review-request.json` 中的全部 artifact logical names；OpenWorker 會把每個 reviewed artifact 補上權威 SHA256，再交給 WorkLedger 保存。

因此 WorkLedger 可回答：

- ChatGPT 實際看過哪些成果；
- 每個成果的 SHA256；
- 哪一版位元內容被接受；
- 是否存在漏看成果卻 PASS 的情況。

實作 commit：`8fef199ebc015a128ae8f514eb0a73c60b40d976`

永久測試 commit：`206e829238ba52e49da8c5577e98c0df19fbe4ef`

## CI 真實暴露出的缺口

CI run `31987861736` 的 pytest job `95265854765` 真實失敗，原因不是 ReviewCycle 產品邏輯，而是 test collection 基礎設施存在兩個歷史缺口：

1. `tests/test_case0003_final_acceptance.py` 會 import `scripts.case0003_final_acceptance`，但 `scripts/` 尚未明確成為 Python package，導致 `ModuleNotFoundError: No module named 'scripts'`。
2. `tests/test_project_knowledge.py` 與 `tests/runtimes/test_project_knowledge.py` 同名，pytest 預設 import mode 發生 module collision。

這些錯誤代表新 review tests 尚未真正跑完整 suite，不能把前面的 commit 誤算為 CI PASS。

## CI 基礎修補

### pytest import mode

`pyproject.toml` 已固定：

```toml
addopts = ["--import-mode=importlib"]
```

避免不同目錄的同名 test module 污染 Python module namespace。

commit：`c792ed57c874abb50b0ec61017744dae1fe8badc`

### scripts package

新增 `scripts/__init__.py`，讓 regression tests 可以正式 import case scripts，而不是依賴執行目錄碰巧出現在 `sys.path`。

commit：`11fe17db9617ee45f14a3e12956a91d046453bcd`

最新 CI run：`31987965335`

目前狀態：`queued`。尚未宣告 PASS。

## Case 0003 REAL 狀態

最新 LLM review gate REAL run：`31987851129`

目前仍為 `pending`，尚未由 UL7 接單。

因此目前權威狀態是：

- Review governance code：已實作；
- Drive bounded auto-discovery：已實作；
- full artifact coverage before PASS：已實作；
- permanent tests：已加入；
- full CI：等待最新 run；
- UL7 REAL Review Bundle：尚未產生；
- ChatGPT REAL receipt：尚未產生；
- accepted/delivered pointer：不得因 mechanical PASS 提前移動。

## 下一步

1. 等最新 CI `31987965335` 真實跑完；若 pytest 還失敗，繼續修真正 collection/test 問題。
2. UL7 恢復後讓 Case 0003 產生第一個 REAL Review Bundle。
3. 確認 Review Bundle 已同步到 `OpenWorker-ChatGPT-Review-TEMP`。
4. ChatGPT 透過 Google Drive connector 讀取完整成果。
5. 產生第一份正式 `PASS / TUNE / TOOL_GAP` receipt。
6. 若 TUNE：保存 before/after/reason/expected effect，建立 child revision 後 REAL 重跑。
7. 若 TOOL_GAP：記錄 gap capability / owning repo / gap description / verification plan，進入 REWORK_REQUIRED，補工具與永久測試後再 REAL 重跑。
8. 所有成果、參數調整、工具缺口、修補與重新驗證全部保留在 WorkLedger revision history。
