# OpenWorker LLM 成果審查閉環：第一批進度

日期：2026-08-17
狀態：IMPLEMENTING

## 本批完成

### 1. 建立 Google Drive Review Exchange

已建立 ChatGPT 可存取的臨時 Review folder：

- `OpenWorker-ChatGPT-Review-TEMP`
- folder id: `1A4BnZEcFe2WIhcperRd4QSpxoSUN_ARR`

Drive 只作暫存 handoff，不取代 WorkLedger。

### 2. 新增共用 `ReviewCycle`

檔案：`coworker/review_cycle.py`

已具備：

- bounded Review Bundle builder
- artifact SHA256 manifest
- review-request.json
- current parameters snapshot
- parameter allowlist
- owning capability/repo
- Google Drive Desktop sync handoff
- atomic copy + SHA tree verification
- structured LLM receipt
- PASS/TUNE/FAIL governance
- TUNE before-value 驗證
- TUNE parameter allowlist
- tuning child revision
- FAIL -> REWORK_REQUIRED

重要原則：ChatGPT 的 Drive Connector token 不屬於 GitHub Action。P0 transport 使用 `OPENWORKER_REVIEW_DRIVE_ROOT` 指向 Google Drive for desktop 本機同步資料夾；未設定時 handoff fail-closed。後續可另補 service account/API transport。

### 3. 新增工具缺口探測路由

檔案：`coworker/review_gap.py`

新增 `TOOL_GAP` 語義：

- 不是參數問題
- 不能用 TUNE 掩蓋
- 必須提供：
  - `owning_repo`
  - `gap_capability`
  - `gap_description`
  - `verification_plan`
- 正規化為 WorkLedger `REWORK_REQUIRED`
- receipt、reviewed artifact SHA、owner、修補驗證計畫永久保留

因此成果審查層現在同時是：

1. 品質驗收器
2. 參數調整器
3. 工具缺口探測器
4. owning repo 返工路由器

### 4. 永久測試

新增：

- `tests/test_review_cycle.py`
- `tests/test_review_gap.py`

鎖定：

- Review Bundle 不覆蓋
- Drive handoff SHA 一致
- PASS 留 required LLM Semantic Review
- TUNE 建 child revision
- 非 allowlisted parameter 拒絕
- before-value 不一致拒絕
- TOOL_GAP -> REWORK_REQUIRED
- TOOL_GAP 缺 owner/capability/description/verification plan 時 fail-closed

## 新的正式閉環

```text
REAL 工具成果
 -> 機械/physical reopen
 -> Review Bundle
 -> Google Drive TEMP
 -> ChatGPT 看成果
      |
      +-- PASS
      |    -> receipt
      |    -> acceptance gate
      |
      +-- TUNE
      |    -> parameter delta
      |    -> child revision
      |    -> owning capability rerun
      |    -> parent/child 成果比較
      |    -> 再 Review
      |
      +-- TOOL_GAP
           -> gap capability
           -> owning repo
           -> REWORK_REQUIRED
           -> 補真正工具缺口
           -> permanent test
           -> child revision
           -> REAL rerun
           -> 再 Review
```

## 尚未完成

1. WorkLedger revision kind 尚未獨立加入 `tuning`；目前 tuning 以 child progress revision + `revision_role=tuning` 表示，後續應正式 schema 化。
2. Case 0003 Final Acceptance 尚需切成：機械 gate PASS -> Review Bundle/Handoff -> WAITING_LLM_REVIEW；不能立即 accepted/delivered。
3. Action 尚需加入 Google Drive Desktop sync root 探測與 handoff step。
4. ChatGPT review receipt 尚需正式回傳入口（CLI/API）與身份/provenance。
5. TOOL_GAP 後尚需自動呼叫知識圖譜/能力 registry 定位 owning repo，並將修補提交/測試/run evidence 串回原 work revision chain。
6. Google Drive TEMP bundle 成功 review 後需有 bounded cleanup policy，但 manifest/receipt/SHA 不能刪除。

## Case 0003 下一步

玉井橋第一個實案會把：

- SceneX screenshot
- Blender render
- delivery HTML
- terrain evidence

打包到 Review Bundle。ChatGPT 實際檢查後：

- 視角/尺度/構圖問題 -> TUNE
- SceneX/Blender/Terrain 能力不足 -> TOOL_GAP
- 全部符合 -> PASS

只有 PASS 才能推進 WorkLedger accepted/delivered pointer。
