# 案例 0003：玉井橋 — OpenWorker Final Acceptance 第四批進度

> 更新時間：2026-08-17 09:51（Asia/Taipei）
>
> 主責 repo：`liuxb99/openworker`
>
> 狀態：`VERIFYING / UL7 FINAL ACCEPTANCE PENDING`

## 本批目標

把 Case 0003 從「歷史 REAL run 成功」升級成 OpenWorker 自己可重開、可驗收、可返工、可追蹤 revision 的真正工作閉環。

## 已完成

### 1. Final Acceptance 改成每次獨立 child revision

提交：`fcae4bdf3f907a82acc8b98f10474c409a9a8ca9`

修正前，若 WorkLedger HEAD 尚為 `open/verifying`，Final Acceptance 可能直接把 fresh artifact/check 寫進既有 revision；同名 artifact 又可能被當成 duplicate 忽略，會破壞 append-only / 可比較 revision 語義。

修正後：

```text
current HEAD
  ↓
Final Acceptance attempt
  ↓
new child revision
```

- 若 HEAD=`REWORK_REQUIRED`：建立 `rework` child revision。
- 其他狀態：建立 `acceptance` child revision。
- fresh DTM/AOI/Consumer/Blender/SceneX/OS/Delivery evidence 只寫入該 attempt revision。
- 同 revision 內 duplicate artifact 不再靜默忽略；視為程式錯誤。
- 每個 attempt 另存 `work-ledger-final-acceptance-<revision_id>.json`，`work-ledger-final-acceptance.json` 只作 latest pointer 輸出。

### 2. shared DTM catalog 明確標示 external canonical provenance

`D:\TaiwanDTM\catalog\dtm_catalog.sqlite` 不在 Case workspace 內，但它是跨工作共用 canonical source，而不是 workspace 產物。

Final Acceptance 現在在 provenance 明確標記：

`scope=shared-canonical-external`

避免把「workspace bounded artifact」和「權威共享基礎資料」混為一談。

### 3. Final Acceptance concurrency 改成 protected single writer

提交：`5f70ce031ea93b1ba1ceb7b4ec625e8e212bbf12`

workflow：`.github/workflows/case-0003-yujing-bridge-ul7.yml`

現在：

```yaml
concurrency:
  group: case-0003-openworker-final-acceptance-ul7
  cancel-in-progress: true
```

原因：accepted/delivered pointer 是 protected pointer，不能同時有兩個 Final Acceptance run 競爭寫入。

實際效果已驗證：

- run `31985238498` → `cancelled`
- run `31986064238` → `cancelled`

舊 pending attempts 已被 supersede，不再互相卡住。

### 4. 最新唯一 Final Acceptance attempt

目前最新：

- run：`31986095405`
- run number：`13`
- commit：`5f70ce031ea93b1ba1ceb7b4ec625e8e212bbf12`
- workflow：`Case 0003 Yujing Bridge OpenWorker Final Acceptance UL7`
- 狀態：`pending`

因此目前**不得宣告 Case 0003 已重新 CLOSED**。

只有 UL7 真正接單並完成以下鏈後才可更新：

```text
UL7 identity fail-closed
→ fresh SceneX Region Pack
→ Godot 4.6.3 D3D12 REAL browse
→ fresh 1280×720 screenshot/evidence
→ DTM SQLite reopen/quick_check
→ AOI JSON reopen
→ Consumer contract reopen
→ Blender REAL reopen .blend
→ OS website reopen
→ Delivery tree check
→ WorkLedger required checks
→ accepted_revision_id
→ delivered_revision_id
```

## 目前阻塞

不是產品 evidence 已失敗，而是 latest Final Acceptance run 尚未取得 UL7 runner。

這和「驗收失敗」不同，不能建立錯誤的 owning repo rework。只有 business job 開始執行並出現第一個 REAL check failure，才能定位真正 owning repo。

## 下一步

1. 追 `31986095405` 是否由 UL7 接單。
2. 一旦執行，逐步讀 job step/log。
3. 第一個 REAL failure：
   - WorkLedger → `REWORK_REQUIRED`
   - 記錄 `gap_owner_repo`
   - 修真正 owning repo
   - child rework revision
   - 重跑相同 Final Acceptance。
4. 全部 required checks PASS 後才允許：
   - `accepted_revision_id = current acceptance revision`
   - `delivered_revision_id = accepted_revision_id`
   - Case 0003 狀態重新改成 `CLOSED / OPENWORKER REAL VERIFIED`。

## 本批結論

這批不是增加更多「成功文字」，而是修掉兩個會破壞工作治理的實際缺口：

- Final Acceptance 不可寫進舊 revision；
- Final Acceptance 不可多 run 同時競爭 protected pointer。

目前 Case 0003 正式狀態仍是：

`VERIFYING / UL7 FINAL ACCEPTANCE PENDING`
