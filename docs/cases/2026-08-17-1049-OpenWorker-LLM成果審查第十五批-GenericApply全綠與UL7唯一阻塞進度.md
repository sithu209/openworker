# OpenWorker LLM 成果審查第十五批：Generic Apply 全綠與 UL7 唯一阻塞進度

時間：2026-08-17 10:49（Asia/Taipei）

## 本批結論

Hosted CI 已對最新 Generic LLM Review Apply 治理完成完整驗證：

- CI run：`31989131493`（#321）
- pytest：SUCCESS
- gui-unit：SUCCESS
- gui-e2e：SUCCESS

這表示本輪新增與收斂的治理能力已通過完整 hosted gate：

1. Review receipt 必須綁定 exact `manifest.json` SHA256。
2. `manifest.sha256` sidecar 可直接供 Google Drive / ChatGPT 審查端回填 receipt binding。
3. PASS 必須完整覆蓋 Review Bundle artifact，且 OpenWorker 以權威 SHA enrich reviewed artifacts。
4. TUNE 產生原生 `kind=tuning` child revision。
5. Generic receipt apply 不再依賴 Case 0003 常數。
6. Generic PASS 預設只 accept，不暗中 deliver；只有顯式 delivery metadata 才可 deliver。
7. Generic TUNE / TOOL_GAP / FAIL 都由 WorkLedger 保存不可覆寫歷史。
8. Generic Windows self-hosted apply workflow 可用 `workspace + work_code + revision_id + receipt_path + assigned_host + runner_label` 執行。

## #317 兩個失敗的收斂

CI #317 曾出現：

- `1457 passed`
- `4 skipped`
- `2 failed`

兩個失敗均在 `tests/test_review_pass_coverage.py`，原因是舊 coverage test 尚未帶新增加的 `bundle_manifest_sha256`，因此被 exact bundle binding 前置 gate 正確拒絕。

修正 commit：

`c5d0611ad2a12ce368a8fe795a3f0bf183e78dac`

修法沒有放寬產品規則，而是讓 coverage 測試先符合新的 manifest binding contract，再繼續驗證：

- partial artifact coverage 必須 fail；
- complete artifact coverage 會以 review-request 的權威 SHA enrich receipt evidence。

## Generic receipt apply

核心實作：

- `script/openworker_apply_llm_review.py`
  - commit `eb3a79bf5285c884b881c740b6211795ebbc83b4`
- `.github/workflows/openworker-apply-llm-review-win11.yml`
  - commit `352a18fb7288d14002796c02b83e7990d445e396`
- 永久測試
  - commit `2d5c66a5c6a69817fa97f9fa46329d2cb7ca4d64`

Generic apply 的權威輸入為：

```text
workspace
+ work_code
+ revision_id
+ receipt
+ immutable review-request.json
+ exact bundle_manifest_sha256
```

### PASS

沒有明確 delivery metadata 時：

```text
reviewed revision
→ LLM Semantic Review PASS
→ accepted_revision_id = revision
→ delivered_revision_id 不動
```

### TUNE

```text
reviewed revision
→ TUNE
→ native kind=tuning child revision
→ parameter delta immutable
→ REAL rerun
→ 新 bundle
→ 再審查
```

### TOOL_GAP / FAIL

```text
reviewed revision
→ rework_required
→ owning repo / gap capability / verification plan
→ repair real tool
→ permanent tests
→ REAL rerun
→ 新 review revision
```

## Case 0003 REAL 狀態

最新 Case 0003 REAL workflow：

- run `31988901946`
- run number `#22`
- status：`queued`

UL7 仍尚未接單，因此本輪不能宣稱 Case 0003 REAL review 已完成。

這個 blocker 的分類仍然是：

`INFRASTRUCTURE_WAITING`

不是：

- `TOOL_GAP`
- `REWORK_REQUIRED`
- semantic review failure

目前 GitHub Connector 對 self-hosted runner inventory/status API 缺少權限，無法從 Connector 直接判定 UL7 是 offline、busy 或 runner service / label 狀態；這是 Connector 權限邊界，不應污染 OpenWorker 產品缺口分類。

## 目前閉環

```text
REAL execution
→ mechanical reopen / physical checks
→ immutable Review Bundle
→ manifest.json
→ manifest.sha256
→ Google Drive TEMP review exchange
→ ChatGPT review
→ PASS / TUNE / TOOL_GAP / FAIL
→ manifest-bound receipt
→ Generic receipt apply
→ WorkLedger immutable revision history
→ accept / tuning / rework
→ explicit delivery only after accepted revision
```

## 下一步

P0 已由 hosted CI 證明的部分不再反覆改寫。下一個真正的端到端證據應是：

1. UL7 runner 接到 Case 0003 #22 或更新後同一 single-writer workflow。
2. fresh SceneX REAL browse + mechanical acceptance 全通過。
3. Review Bundle 寫入 Google Drive TEMP exchange。
4. ChatGPT 讀取實體 artifact、`review-request.json`、`manifest.sha256`。
5. 產生第一份真實 PASS / TUNE / TOOL_GAP receipt。
6. 使用 Generic receipt apply 回收 verdict。
7. WorkLedger 保留完整 execution → artifact → review → parameter/tool-gap decision → child revision / acceptance provenance。

在 UL7 接單前，Hosted governance 已收斂；後續不應把 infrastructure waiting 誤寫成產品成功或產品失敗。
