# Case 0005：PDF 工程圖 → Native DWG REAL 完整閉環手冊

更新日期：2026-08-16
主責位置：`liuxb99/openworker`
狀態：`IMPLEMENTING / REAL INPUT LOCATOR RUNNING`

## 1. 案例目標

使用者提供真實工程 PDF，只給 OpenWorker/go-tool-runtime：

```text
goal = PDF 工程圖轉 DWG
input = engineering_pdf[source]
```

系統須由 Tool Graph 找出 owning capabilities、authority gate、runner、輸入輸出與驗證方式，最後取得可重新開啟且通過 native fidelity 的非空 Native DWG。禁止把 PDF raster 包進 DWG 假裝完成。

## 2. 正式鏈

```text
engineering_pdf[source]
→ pdf.drawing.reconstruct
→ engineering_drawing_ir[candidate]
→ OS Artifact Registry / Review
→ engineering.review.evidence.export
→ engineering_ir_approval_evidence[validated]
→ engineering.review.approve
→ engineering_drawing_ir[approved]
→ dwg.cad.execute
→ native_dwg[validated]
→ reopen/native fidelity PASS
→ execution evidence → KnowGraphGo
```

責任：go-pdf-drawing-reconstructor=PDF/IR candidate；AI-Engineering-OS=Artifact Registry/Review/authority；DWG_todo=Native DWG；go-tool-runtime=capability/plan/dispatch；KnowGraphGo=graph/explain/learning；OpenWorker=workspace/case orchestration。

## 3. REAL 輸入識別與 ingest

ChatGPT Library 已確認最新施工圖：

```text
name = 鋼便橋施工圖(2).pdf
size = 4,763,184 bytes
```

Library file reference 不是 self-hosted runner 的本機 path，禁止把「Library 可讀」當成「Action 已拿到」。因此新增：

`.github/workflows/case-0005-input-locator-ul7.yml`

commit：`fbc3e7a21efef6f1139725ad3b6f91560ac1d1fb`

它只在 `DESKTOP-UL7V2VV` 的 allowlist roots 搜 exact basename；多候選若 SHA 不同 fail closed；找到後複製到：

`D:\AI-Work\jobs\0005-PDF-DWG\input\鋼便橋施工圖(2).pdf`

並寫：

`D:\AI-Work\jobs\0005-PDF-DWG\evidence\case0005-input-ingest.json`

證據包含 source/destination path、size、SHA256、runner、run id。找不到必須 `CASE0005_SOURCE_NOT_FOUND`，不得拿相似 PDF/報告替代。

首次 REAL locator：`31942540901`。本次更新時仍 `queued`，尚未取得 runner-local SHA。

## 4. 第七批 CI 修復

### AI-Engineering-OS

Run `31942252286` 真實失敗於 syntax gate：`internal/engineeringirauthority/authorize.go` 在 `append(approved, '\n')` 後少 statement boundary，導致 `outSum` parser error。

已修：`f348fa9ffdfbd34b6609c02b1f5356cf3c883cfc`。

同一 run 亦證實 GitHub Actions artifact quota 已滿；診斷 artifact upload 不應覆蓋產品 build/test。OS CI module-lock / executable / Golden upload 已改 `continue-on-error: true`：

`e8a633b2ccba5e3266a14e2693194533f0e4a0c4`

最新 OS Local Verification：`31942501840`。本次更新時已在 UL7 執行 `Syntax gate`，尚未 terminal。

### DWG_todo

舊 run `31941945232` 的 Native extractor/Rust tests 已 PASS，blocking failure 是 structural 舊測試仍要求固定 evidence slice 長度。產品新增 `PB-DESIGN-SECTION / SB-DESIGN-SECTION` 後舊 assertion 已過時。

修復：

- `c6a306a54a08d6aba59535701dab3f6ea183769f`
- `883e03c898f3f7100a03fc7e4eab832d095c286e`

最新 full CI：`31942369460`；本次更新時 job `95153291196` 正在 native DWG extractor build，未 terminal。

## 5. CLOSED / REAL VERIFIED 條件

必須同時有：使用者 PDF runner-local path/size/SHA256、fresh Tool Graph plan、PDF reconstruction run/job、candidate IR SHA、OS Artifact ID/revision、Review ID/reviewer/decision、SHA-bound approval evidence、approved IR SHA、DWG run/job、Native DWG size/SHA、independent reopen PASS、native fidelity PASS、all-skipped=false、execution evidence 寫入 KnowGraphGo。

## 6. 下一個 REAL 接續點

1. 追 locator `31942540901` terminal；成功則鎖 exact input SHA。
2. 追 OS `31942501840` 與 DWG `31942369460` terminal；失敗就修 owning repo。
3. 在同一 workspace fresh 產 Tool Graph plan。
4. Action 跑 PDF reconstruction → OS Review/Approval → Native DWG。
5. reopen/native fidelity 後把 execution evidence 回寫 KnowGraphGo。

在 Native DWG 真實產出並 reopen/fidelity PASS 前，不得標 `CLOSED`。
