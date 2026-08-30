# OpenWorker LLM 成果審查第十二批：Manifest 綁定與原生 Tuning Revision 進度

時間：2026-08-17 10:41（Asia/Taipei）

## 本批目標

在 UL7 尚未接單期間，不等待 REAL runner，先補完 LLM Review 閉環剩餘的兩個 P0 治理缺口：

1. LLM review receipt 必須綁定 exact immutable Review Bundle manifest，避免舊 receipt 套到不同 bundle。
2. TUNE 不再以 `progress + revision_role=tuning` 偽裝，WorkLedger 提供原生 `tuning` revision kind。

## 1. Exact manifest SHA binding

`coworker/review_gap.py` 新增：

- `bundle_manifest_sha256(cycle, revision_id)`：對 `.openworker/reviews/<revision_id>/manifest.json` 計算權威 SHA256。
- `_bind_exact_bundle(...)`：所有 `PASS / TUNE / FAIL / TOOL_GAP` finding 在進入 ReviewCycle 前都必須帶 `bundle_manifest_sha256`。
- 缺少 SHA、格式不是 64 位 hex、或 SHA 與本機 immutable manifest 不一致，都 fail-closed。
- 驗證成功後，標準化 receipt 會保留權威 `bundle_manifest_sha256`，因此 durable receipt 可回答「這次模型判定對應的是哪一份 bundle manifest bytes」。

commit：`33de2cb7f15b74c7583e30fafc853a3db6a042ca`

永久測試：

- `tests/test_review_gap.py` 已更新 TOOL_GAP finding 為 manifest-bound。
- 新增 missing binding 與 stale/wrong binding fail-closed regression test。

commit：`d965f2eb0b6d5d991daf1d8ceeac9afb10245ecd`

Case 0002 的 PASS regression test 也改為實際對 `manifest.json` 計算 SHA256，再寫進 receipt；不再製造未綁定的 PASS receipt。

commit：`bafcf550ec424d5c4d31836a8fcd00aa64b17a53`

## 2. WorkLedger 原生 tuning revision

`coworker/work_ledger.py` 的 `_VALID_REVISION_KINDS` 新增 `tuning`：

```text
initial
progress
tuning
rework
acceptance
delivery
acceptance_import
```

commit：`0097c5eae388f5d30fa671031db390ce547435e9`

`coworker/review_cycle.py` 的 TUNE child revision 現在直接使用：

```python
kind="tuning"
```

而不是原本的 `kind="progress"`。`plan.revision_role="tuning"` 仍保留作為語意 metadata，但 revision kind 本身已是權威值。

commit：`088aabd59c05a8e3b860b62db5e2a4471e43bc39`

永久測試新增：

`tests/test_tuning_revision_kind.py`

驗證：

- TUNE 會建立 child revision。
- child `kind == "tuning"`。
- parent pointer 指向被 review 的 revision。
- `source_review_revision_id` 與 parameter delta provenance 保留。

commit：`378ed06e14d886103d213f109b3a4b4edb09b803`

## 3. UL7 runner 狀態與 GitHub Connector 權限邊界

嘗試直接查 repository self-hosted runner API：

`GET /repos/liuxb99/openworker/actions/runners`

GitHub App 回覆 `403 Resource not accessible by integration`。因此目前 Connector 沒有 self-hosted runner administration/read scope，無法直接判斷 UL7 是 offline、busy 或 labels 未匹配。

這是 Connector 權限邊界，不是 OpenWorker 產品 TOOL_GAP。

Case 0003 最新由 review/work-ledger 修改觸發的 REAL run：

- run `31988692836`
- run number `20`
- head `088aabd59c05a8e3b860b62db5e2a4471e43bc39`
- 目前 queued
- run #19 已因 single-writer concurrency 被正常 cancelled

在 UL7 真正接單以前，不生成假 Review Bundle，不生成假 receipt，不把 infrastructure waiting 分類成 TOOL_GAP。

## 4. CI 狀態

最新 generic CI：

- run `31988705583`
- run number `311`
- head `378ed06e14d886103d213f109b3a4b4edb09b803`
- pytest / gui-e2e 已開始執行
- 目前尚未 terminal，因此本批不可宣告 CI PASS。

前一批 CI `31988194969` 已確認 pytest、gui-unit、gui-e2e 全部 SUCCESS；本批需要新的 CI 再驗證 manifest binding + native tuning revision。

## 5. 現在的 review governance

```text
REAL execution
  → mechanical reopen verification
  → immutable Review Bundle
  → manifest.json
  → SHA256(manifest.json)
  → Google Drive temporary exchange
  → ChatGPT reads complete artifacts
  → receipt must bind exact bundle_manifest_sha256

PASS
  → complete reviewed_artifacts coverage + per-artifact SHA
  → LLM Semantic Review PASS
  → accept_revision
  → deliver_revision

TUNE
  → allowlisted parameter delta
  → native tuning child revision
  → REAL rerun
  → compare outcome
  → new immutable Review Bundle
  → re-review

TOOL_GAP
  → owning repo + capability + verification plan
  → REWORK_REQUIRED
  → repair real tool + permanent tests
  → child revision
  → REAL rerun
  → re-review
```

## 下一步

1. 等本批 CI `31988705583` terminal；若失敗，依 log 修真正回歸，不放寬 manifest binding / tuning contract。
2. UL7 接單後取得第一份 Case 0003 REAL Review Bundle。
3. ChatGPT 從 Google Drive 讀 exact `manifest.json` + 全部 artifacts，產生帶 `bundle_manifest_sha256` 的第一份正式 receipt。
4. PASS 才允許 accepted/delivered；TUNE 建 native tuning revision；TOOL_GAP 進 owning repo repair loop。
