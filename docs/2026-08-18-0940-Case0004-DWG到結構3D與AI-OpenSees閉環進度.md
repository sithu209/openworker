# Case 0004 — DWG 到結構 3D 與 AI-OpenSees 閉環進度

日期：2026-08-18
狀態：IMPLEMENTING / STORY REGION REVIEW APPLY RUNNING

## 1. 固定案例權威

- Case：`0004`
- Workspace：`D:\AI-Work\jobs\0004-DWG-TO-3D`
- Assigned host：`DESKTOP-O87PJNR`
- OpenWorker durable manifest：`case-worklists/0004.json`
- 原始 DWG SHA256：`aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6`
- overview SHA256：`5cee03340cbbcad51e412b46b85bda9dcaac22b193586b953bbfd5134039103e`

本文件為 Case 0004 持續案例紀錄。後續每一個 Worklist step、repair、REAL run、receipt、commit、阻塞原因、修復方式與驗收結果都必須追加到本文件，不只記最終結果。

## 2. 已完成 Worklist 步驟實錄

### 2.1 `0004-010` — Locate exact primary DWG

狀態：`PASSED`

REAL evidence：

- run：`32008732425`
- canonical source：`D:\AI-Work\jobs\0004-DWG-TO-3D\input\source.dwg`
- SHA256：`aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6`

Repair 歷史：

- `R-0004-010-001`：duplicate-source ambiguity canonical reconcile，`PASSED`，repair commit `df921bd7268d3a4027d88c5450270b05471b7f34`。
- `R-0004-010-002`：source locator UTF-8 / GitHub output contract，`PASSED`，repair commit `a89981d108ed795a7d9b3c98a0232eec296becd6`。

結論：後續一律以 workspace `input/source.dwg` 與上述 SHA 為 source authority，不再使用舊 SHA。

### 2.2 `0004-020` — Canonical source ingress + OS Project Job + JobBinding

狀態：`PASSED`

REAL evidence：

- run：`32009612975`
- project：`prj_3e0dda459b582aed83e0367c755660e5`
- job：`job_f85f3e01cbe1f998c16ac2b772db4fc1`
- JobBinding：`D:\AI-Work\jobs\0004-DWG-TO-3D\.openworker\job-binding.json`
- OS authority commit：`ca678a1ad47aba8e9386993173aa22eb126120e5`

Repair 歷史：

- `R-0004-020-001`：resolve persisted AI-Engineering-OS authority，`PASSED`。
- `R-0004-020-002`：改用 O87 現有 system Python >=3.10，不依賴 setup-python download，`PASSED`，repair commit `52d223eb48c53e38330b6cbf108380b926d6982d`。
- `R-0004-020-003`：以 REAL ingress evidence reconcile JobBinding，`PASSED`。

### 2.3 `0004-030` — Open primary DWG

狀態：`PASSED`

REAL evidence：

- run：`32011733568`
- job：`job_f85f3e01cbe1f998c16ac2b772db4fc1`
- receipt：`evidence\dwg-cad-local\case0004-open-32011733568\receipt.json`
- source SHA256 與 canonical source 一致。

### 2.4 `0004-040` — Model extents and raw overview render

狀態：`PASSED`

REAL evidence：

- extents receipt：`evidence\dwg-cad-local\case0004-extents-32011900313\receipt.json`
- overview：`dwg\exports\default\visual-search\case0004-overview.png`
- overview SHA256：`5cee03340cbbcad51e412b46b85bda9dcaac22b193586b953bbfd5134039103e`

## 3. `0004-050` Story Region — 詳細過程

### 3.1 初始 candidate 與負證據

早期 candidate inventory 不能直接作 Story Region authority。`R-0004-050-001` 已把錯誤候選正式記成負證據：

- `cluster-x0-y0` REAL query entity count：`904`
- `cluster-x1-y0` REAL query entity count：`0`
- 結論：`cluster-x1-y0` 不得升格 Story Region。

### 3.2 多模態視覺搜尋

實際解碼 review images 後，真正可作樓層平面候選的是 `c-mid-left`：

- source preview：`candidate-overview.png`
- pixel crop：`[0,533,200,133]`
- 畫面內容：可辨識房間、牆線、格網與平面配置；不是 title block / index / 表格。
- Round 3 / Round 4 central/right crop 偏移到表格或文字區，排除。

OpenCAD renderer inverse transform 已核對：10 px margin、X/Y 等比例 fit、Y 軸反轉。由此得到 candidate Model Space bounds：

```text
minX = 44443.25117281456
minY = 44319.71383237175
maxX = 58261.78081822565
maxY = 53992.684584159506
```

### 3.3 REAL `cad.query_bounds` probe

上述 bounds 已經不再只是圖片推測。

REAL probe：

- run：`32088666007`
- machine：`DESKTOP-O87PJNR`
- runner：`DESKTOP-O87PJNR-R004`
- source SHA256：`aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6`
- entity count：`73`
- result：`PASS`

因此 `c-mid-left` 的 pixel → world transform 已被真實 OpenCAD 幾何查詢驗證。

### 3.4 樓層身份證據

候選區域附近 OpenCAD 真實 MTEXT handle `8AF7` 為 `1F` 樓板抬高高度說明，空間位置與候選平面對應。當前多模態判斷採 `story_id=1F`，但仍採 fail-closed：後續柱網、Story Design 或 registration 若與 1F 身份矛盾，必須重新開 Story Region review，不得靜默沿用。

### 3.5 Worklist 真實狀態

2026-08-18 O87 durable Worklist state 已回寫：

- state run：`32090290113`
- machine：`DESKTOP-O87PJNR`
- runner：`DESKTOP-O87PJNR-R004`
- durable revision：`130`
- `0004-010`～`0004-040`：全部 `PASSED`
- `0004-050`：`BLOCKED`
- blocker：`LLM visual review is mandatory before StoryRegion promotion; geometry/text probes are auxiliary evidence only`
- canonical current step：`R-0004-050-002`
- `R-0004-050-002` title：`Review cut images with multimodal LLM before StoryRegion promotion`
- `R-0004-050-002` status：`RUNNING`

這證明目前不應重跑 source ingress / open / overview，也不應越級做柱或 3D；唯一合法主線是完成 LLM review repair。

### 3.6 ChatGPT LLM review receipt

已建立正式中間審查 receipt：

`DWG_todo/review-tmp/case0004/llm-story-region-review-receipt.json`

commit：`ce5fb305a66998c8f69a79d32ae7b10a64c5398e`

決策：`PASS`，允許將上述 REAL-probed bounds 以 `story_id=1F` 進入 governed `cad.set_story_region`。這不是最終交付 acceptance，只是 Story Region promotion gate。

### 3.7 Governed apply workflow

已新增：

`.github/workflows/case-0004-o87-apply-story-region-review.yml`

commit：`225387f3d0f5cccd0387a7cd3a0d38d258d8e05e`

設計順序：

1. O87 使用 generic `[self-hosted, Windows, X64]`，以 `COMPUTERNAME == DESKTOP-O87PJNR` 作固定機器權威。
2. 同步最新版 canonical Worklist；sync 必須保留既有 PASSED evidence 與 active repair，不得重置歷史。
3. 將 ChatGPT review receipt 的 acceptance keys 寫入 `R-0004-050-002`。
4. `pass_step(R-0004-050-002)`；OpenWorker repair semantics 會自動把 parent `0004-050` 從 BLOCKED 解鎖為可執行狀態。
5. 執行 REAL `cad.set_story_region`，story=`1F`，bounds 使用已 probe 的 Model Space bounds。
6. 驗證 Story Region 已 persisted。
7. PASS `0004-050`。
8. 進入 `0004-055`，執行 `cad.list_story_column_candidates`。
9. 回寫 `review-tmp/case0004/story-region-column-candidates.json`。

截至本次文件更新：`story-region-column-candidates.json` 尚未回寫，因此**不得宣告 `0004-050` 或 `0004-055` 已完成**。

## 4. `0004-055` 柱候選與視覺確認

最新版 canonical operator 已正式支援 `cad.list_story_column_candidates`。

規則：

- 必須已有 confirmed Story Region。
- 真實 inspect Story Region 內 OpenCAD entities。
- 以 bounds width/depth/aspect/area 產生 geometry shortlist。
- authority 固定為 `none`。
- `review_required=true`。
- 不得因為接近正方形就自動認定為柱。
- 後續至少選出兩個經視覺確認的 column handles，才能進 `cad.design_story_structure`。

目前狀態：等待 3.7 governed workflow 的 REAL receipt。

## 5. `0004-060` Story Design 預定驗收

只有 055 視覺確認 column handles 後才允許執行：

`cad.design_story_structure`

輸出與驗收：

`confirmed column handles → Column Authority → Column Graph → Primary Beam → Floor Bay → Secondary Beam → design.json + design.png`

`design.png` 必須再次做視覺審查，不能只看 JSON count。

## 6. 多樓層 materialize / registration 與 AI-OpenSees 邊界

不得把單層 Story Design 的暫時柱 placement 直接送 AI-OpenSees。單層模型可能存在 same-story zero-height member；真正 3D 柱必須在多樓層 registration 後由 `MaterializeColumnAuthority` 連接相鄰 story placements，形成 `column-link-<lower>-<upper>`。

正式鏈固定為：

`Story Design reviewed → materialize stories → anchors → registration/residual validation → Stage 08 V1 structural authority → AI-OpenSees → Stage 11 structural 3D`

Stage 08 authority：

- `structural-line-model.json`
- `column-authority.json`
- `v1-building-skeleton.json`

MCT bridge fail-closed 規則：missing node、duplicate id、非有限座標、same-node topology、coincident endpoints、zero geometric length 全部拒絕。

## 7. AI-OpenSees production gate

已建立 `.github/workflows/case-0004-o87-ai-opensees-production.yml`。

只有 Stage 08 真實 `structural-line-model.json` 與 sibling `v1-building-skeleton.json` 存在才允許：

`structural-line-model/v1 → deterministic MCT → latest AI-OpenSees C++ CLI → validate`

目前只把已證實的 validation 能力當 gate；若 AI-OpenSees 最新 main 新增正式 solve/analysis，必須重新讀最新 contract 後才能宣稱「結構分析完成」。

## 8. 3D、Blender 截圖與最終交付硬性驗收

最終完成條件不是「3D 檔存在」。完整鏈：

```text
Story Region confirmed
→ Story Design reviewed
→ materialize stories
→ Story anchors / registration confirmed
→ Stage 08 structural-line-model/v1
→ AI-OpenSees gate PASS
→ Stage 11 Building structural 3D
→ production GLB
→ Blender 5.2 REAL reopen
→ perspective render PNG
→ native AC1032 ACIS Solid3D DWG
→ OpenCAD DwgReader reopen / second validation
→ OS Artifact Registry
→ Drive Review Bundle
→ ChatGPT visual review receipt
→ approved Delivery Revision
→ final delivery validation
```

Blender 至少保留一張整體透視 PNG；後續視成果增加正立面、側立面或樓層局部圖。所有圖片必須由 ChatGPT 實際看過後才能通過視覺 QC。

## 9. 工具／治理修復紀錄

本案例已暴露並補過的主要缺口：

1. 固定 runner 不應依賴 `O87` custom label；改用 generic self-hosted Windows/X64 + persisted `assigned_host` / `COMPUTERNAME` gate。
2. go-tool 新增 CaseWorklist-aware capability：`dwg.cad.execute.case-worklist`，明確要求 `case_step`。
3. canonical CAD operator 已正式 allowlist `cad.list_story_column_candidates`。
4. 新增 read-only column candidate shortlist，authority 不得自動升格。
5. structural-line-model → MCT bridge 加入 zero-length / coincident endpoint / non-finite coordinate fail-closed。
6. Worklist sync semantics 已核對：保留 PASSED 歷史與 active repair，不得覆寫既有完成證據。
7. Story Region 必須經多模態 LLM review；REAL geometry probe 只能作輔助證據，不能單獨繞過 review gate。

## 10. 下一個 canonical action

目前唯一正確下一步：等待／檢查 `case-0004-o87-apply-story-region-review.yml` 的 REAL 執行結果。

若成功：

1. 確認 `R-0004-050-002 = PASSED`。
2. 確認 `0004-050 = PASSED` 且 persisted Story Region 為 `1F`。
3. 讀取 `story-region-column-candidates.json`。
4. ChatGPT 視覺確認 column handles。
5. PASS `0004-055`。
6. 進 `0004-060 cad.design_story_structure`。

若失敗：只修實際 failure owning contract，將 failure、log/run/job、修復 commit 與重跑結果追加到本文件，再沿同一路徑重跑；不得另開假閉環。
