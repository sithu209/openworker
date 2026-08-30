# OpenWorker LLM 成果審查第九批：完整覆蓋測試收斂進度

時間：2026-08-17 10:31（Asia/Taipei）

## 本批目標

延續 Google Drive → ChatGPT → WorkLedger 的成果終驗治理，將 hosted CI 從「collection 可執行」收斂到新完整成果覆蓋規則可被全套測試正式驗證。

## 已確認

CI run 31988051805 已能完整收集並執行 pytest，不再出現 scripts package 或同名 test module collection collision。

實際結果：1453 passed、4 skipped、2 failed。

剩餘兩個失敗均是舊測試契約未跟上新治理規則，而不是 ReviewCycle 產品能力失敗：

1. Case 0002 PASS receipt 舊測試只聲明 reviewed_artifacts=[storyboard-pptx]，但 review request 實際有 5 個 immutable artifacts。新規則正確拒絕不完整 PASS。
2. Case 0003 contract test 以原始字串搜尋 accept function 名稱，誤命中註解，不是程式真的存在提前 acceptance 呼叫。

## 本批修補

### Case 0002 完整成果覆蓋測試

commit：75a093d9981e3cfc76bd2343a9319c5fe47aa23b

測試改為讀取該 revision 的 `.openworker/reviews/<revision_id>/review-request.json`，再由權威 artifacts 清單建立 reviewed_artifacts。沒有放寬 PASS 規則。

因此永久規則仍然是：ChatGPT PASS 必須覆蓋該 Review Bundle 的全部 immutable artifacts，且 receipt 之後由 OpenWorker 綁定權威 SHA256。

### Case 0003 contract false-positive

commit：97589a8b9af6b0581fe97e5a81b2c0bf53ed9e4a

僅把註解文字改為不包含 contract test 搜尋的函式 token。實際 handoff 邏輯沒有新增任何提前 acceptance/delivery 路徑。

## 最新 CI

CI run 31988194969（CI #302）已由 commit 97589a8b... 觸發，目前 in_progress。

在此 run terminal 且 pytest/gui-unit/gui-e2e 全綠之前，本批狀態仍為 VERIFYING，不標記完成。

## 不變的治理原則

REAL → mechanical reopen/check → immutable Review Bundle → Google Drive TEMP handoff → ChatGPT 完整查看 → PASS/TUNE/TOOL_GAP。

PASS：全部成果覆蓋 + SHA binding → accepted → delivered。

TUNE：保存觀察、before/after、理由、預期效果 → child revision → REAL 重跑 → 前後比較。

TOOL_GAP：保存 gap capability、owning repo、描述、驗證計畫 → REWORK_REQUIRED → 修 owning repo + permanent test → child revision → REAL 重跑 → 再審。

任何舊測試都不能作為放寬這些治理規則的理由；應更新測試以符合新 authoritative contract。
