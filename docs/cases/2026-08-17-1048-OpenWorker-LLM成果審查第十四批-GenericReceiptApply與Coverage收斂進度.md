# OpenWorker LLM 成果審查第十四批：Generic Receipt Apply 與 Coverage 收斂進度

時間：2026-08-17 10:48（Asia/Taipei）

## 本批目標

把 Google Drive / ChatGPT 審查結果從「案例專用回收腳本」提升成所有 OpenWorker 工作可共用的 WorkLedger receipt apply 入口，同時維持 exact manifest binding、完整 artifact coverage、native tuning revision 與 fail-closed 不變式。

## CI 暴露的真實缺口

CI #317 / run `31988922760` 的 pytest 完整執行結果：

- 1457 passed
- 4 skipped
- 2 failed

兩個失敗都位於 `tests/test_review_pass_coverage.py`，不是產品邏輯退化，而是舊 PASS coverage 測試沒有帶新加入的 `bundle_manifest_sha256`，因此在 coverage assertion 前先被 exact bundle binding 正確拒絕。

修復原則：不放寬 manifest binding。測試先帶 authoritative manifest SHA，再驗原本要驗的 partial/full artifact coverage 行為。

修復 commit：

- `c5d0611ad2a12ce368a8fe795a3f0bf183e78dac`

## Generic receipt apply

新增：

- `scripts/openworker_apply_llm_review.py`

commit：

- `eb3a79bf5285c884b881c740b6211795ebbc83b4`

能力：

1. 以 `workspace + work_code + revision_id` 綁定唯一 WorkLedger 工作版本。
2. 從 `.openworker/reviews/<revision>/review-request.json` 讀取 immutable `allowed_parameter_keys` 與 `current_parameters`，不接受 caller 另造調參契約。
3. 透過 `apply_review_finding()` 驗 exact `bundle_manifest_sha256`。
4. PASS：只移動 `accepted_revision_id`。
5. 若 caller 明確提供 `--delivery-json`，PASS 才另外移動 `delivered_revision_id`。
6. TUNE：產生 native `kind=tuning` child revision。
7. TOOL_GAP / FAIL：保持 WorkLedger rework governance，不接受、不交付。
8. 寫入 `acceptance/openworker-review/llm-review-apply-<revision>.json`。

這樣 generic 層不再暗藏 Case 0003 的 job code、delivery ID 或 website 路徑。

## Generic Win11 workflow

新增：

- `.github/workflows/openworker-apply-llm-review-win11.yml`

commit：

- `352a18fb7288d14002796c02b83e7990d445e396`

workflow_dispatch 輸入：

- workspace
- work_code
- revision_id
- receipt_path
- assigned_host
- runner_label
- optional delivery_json

治理：

- `runs-on: [self-hosted, Windows, X64, <runner_label>]`
- 第一個 step 再以 `COMPUTERNAME == assigned_host` fail-closed。
- work-code 作為 concurrency group，避免同一 work 的 receipt apply 競跑。
- TUNE / TOOL_GAP / FAIL 被視為「治理結果成功寫入」而不是 infrastructure failure，所以 workflow 可綠；真正 contract/host/path/apply exception 才紅。

## 永久測試

新增：

- `tests/test_openworker_apply_llm_review.py`

commit：

- `2d5c66a5c6a69817fa97f9fa46329d2cb7ca4d64`

鎖定：

- PASS generic apply 只能 accept，沒有 explicit delivery metadata 時不得偷 deliver。
- TUNE generic apply 必須建立 native `tuning` child revision，保留 parent pointer 與 parameter delta。

## 最新驗證狀態

修復後最新 CI：

- run `31989131493`
- CI #321
- 目前已進入實際執行，pytest/gui-unit/gui-e2e 尚未 terminal。

因此本文件不宣稱本批 CI 已全綠。

## Case 0003 REAL 狀態

Case 0003 最新 REAL Final Acceptance UL7 仍為：

- run `31988901946`
- #22
- status `queued`

UL7 尚未接單，所以目前仍分類為 infrastructure waiting，不是 TOOL_GAP，也沒有生成新的 Drive Review Bundle。

## 現在完整回收鏈

```text
REAL execution
→ immutable Review Bundle
→ manifest.json + manifest.sha256
→ Google Drive
→ ChatGPT full artifact review
→ receipt with exact bundle_manifest_sha256
→ generic Win11 receipt apply
→ WorkLedger PASS / TUNE / TOOL_GAP / FAIL
   PASS → accepted
          → optional explicit delivery
   TUNE → native tuning child revision
   TOOL_GAP / FAIL → REWORK_REQUIRED
```

## 下一步

1. 追 CI #321 到 terminal；若失敗，直接修實際失敗，不放寬治理規則。
2. UL7 一旦接 Case 0003 #22，追到 fresh SceneX/Blender mechanical reopen 與 Drive handoff。
3. Drive bundle 出現後，ChatGPT 讀取實際 artifacts，產生第一份 manifest-bound REAL receipt。
4. 用 generic Win11 apply workflow 回收 verdict；只有 PASS 才移 accepted pointer，delivery 仍需顯式 metadata。
