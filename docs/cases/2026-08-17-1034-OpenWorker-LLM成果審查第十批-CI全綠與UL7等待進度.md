# OpenWorker LLM 成果審查第十批：CI 全綠與 UL7 等待進度

時間：2026-08-17 10:34 +08:00
狀態：IMPLEMENTING / HOSTED CI GREEN / UL7 INFRASTRUCTURE_WAITING

## 本批結論

本批先收斂前一輪 CI 暴露的測試相容性問題，且不放寬任何 Review governance 規則。

最新正式 CI run `31988194969` 中：

- `gui-unit`：SUCCESS
- `pytest`：SUCCESS
- `gui-e2e`：執行中（本文件建立時）

`pytest` 已證明前一輪兩個剩餘失敗均已修復：Case 0002 PASS 測試現在遵守完整成果覆蓋規則；Case 0003 contract test 不再因註解字串誤判。

## 已完成修補

### 1. Case 0002 PASS 測試改為 authoritative artifact coverage

commit：`75a093d9981e3cfc76bd2343a9319c5fe47aa23b`

舊測試只在 receipt 中列出 `storyboard-pptx`，但新治理規則要求 PASS 必須覆蓋 `review-request.json` 內全部 immutable artifacts。測試現改為直接從 review request 讀取全部 logical artifact names，再生成 PASS receipt。

這是更新舊測試以符合新 contract，不是降低 contract。

### 2. Case 0003 review gate contract test 移除註解誤判

commit：`97589a8b9af6b0581fe97e5a81b2c0bf53ed9e4a`

舊 contract test 會搜尋 `accept_revision(` 字串；handoff 腳本註解內出現同字串，造成 false positive。只修改註解，不修改任何產品 gate。

Case 0003 仍維持：

`mechanical PASS -> required LLM Semantic Review pending -> Drive handoff -> WAITING_LLM_REVIEW`

在正式 receipt PASS 前，accepted/delivered pointer 不得移動。

## CI 證據

前一 run `31988051805` 已完整執行 pytest：

- 1453 passed
- 4 skipped
- 2 failed

兩個 failed 均為上述舊測試未跟上新治理規則。

修補後 run `31988194969` 的 `pytest` 已 SUCCESS。

## Case 0003 REAL 狀態

最新 Case 0003 workflow：

- run：`31988194815`
- run number：17
- workflow：`Case 0003 Yujing Bridge OpenWorker Final Acceptance UL7`
- 狀態：`pending`

前一 run `31987851129` 已因 single-writer concurrency 被取消，屬正常 supersede，不算產品失敗。

因此目前 Case 0003 的阻塞分類是：

`INFRASTRUCTURE_WAITING / UL7 runner 尚未接單`

不是：

`REWORK_REQUIRED`

也不是：

`TOOL_GAP`

## 下一步

1. 等 UL7 接到最新 Case 0003 run。
2. 重新生成 fresh SceneX / Blender / delivery evidence。
3. OpenWorker mechanical reopen checks 全 PASS 後建立 immutable Review Bundle。
4. handoff 至 Google Drive TEMP exchange。
5. ChatGPT 讀取完整成果並產生 PASS / TUNE / TOOL_GAP receipt。
6. PASS 才 accepted/delivered；TUNE 開 child revision；TOOL_GAP 路由 owning repo 修補後 REAL 重跑。

## 本批原則

Hosted CI 是否通過、UL7 runner 是否在線、產品成果是否通過 LLM semantic review，是三個獨立 gate，必須分開記錄，不得互相冒充完成。
