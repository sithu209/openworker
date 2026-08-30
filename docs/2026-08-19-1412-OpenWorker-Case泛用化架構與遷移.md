# OpenWorker Case 泛用化架構與遷移

更新時間：2026-08-19 14:26 +08:00

## 問題

OpenWorker Go control plane 先前仍存在 Case ID / step ID 硬編碼，若每增加 Case 0006、0007 都要修改 Go 核心，會破壞「單一泛用 Go 主控」目標。

## 已完成

### 1. Bootstrap 改為 manifest/spec authority

Commit：`cfb82ca27a3393a52721eac846e0fcedf7d13106`

Case Engine 不再以 0004 / 0005 白名單判斷合法性，只做：

- case_id 字元/path safety；
- worklist `case_id / assigned_host / workspace_root / revision` authority 驗證；
- dependency graph 驗證；
- spec `case_id` 一致性。

真正 Case authority 是 manifest/spec，不是 Go switch。

### 2. CLI 改為 manifest-driven discovery

Commit：`30041542041d197b262eebb7233f7ce3d785ca2a`

`openworker case status/bootstrap/continue <CASE_ID>` 動態讀：

- `case-worklists/<CASE_ID>.json`
- `case-specs/<CASE_ID>.json`

並由 worklist 取得 assigned host / workspace。CLI 不再寫死 0004 / 0005。

### 3. Action Mapper Registry 已落地

Commits：

- `3d797a4dfbacef165f1f6d89f3b10f24619700fa`
- `0b483ce706da0d19660c9d19b11705b093707912`
- `fdb69054140e915be755c05205b1b1186fd62b4a`
- `652b15a6312e2df8340ffbf661ab3ca9dd291fa4`

Case Engine 的正常 dispatch 已不再走 step-id switch，而是：

`worklist allowed_action`
→ `Action Mapper Registry`
→ bounded validated inputs
→ optional manifest-action → executor-capability alias
→ `:8848` durable queue

目前 registry 已支援：

- `cad.build_story_index`
- `comfyx-studio.director.preproduction`
- `comfyx-studio.storyboard.plan`
- `comfyx-studio.storyboard.real-bind`
- `presentation.openmaic`
- `openworker.case.publish-artifacts`
- `openworker.review.await-drive`

Case 0004 的 `cad.build_story_index` 與 executor capability `dwg.story_index.execute.case-worklist` 差異已用顯式 alias registry 保留，不靠 Case ID 特例。

### 4. 泛用 Case 回歸測試

Commits：

- `15c62f8afc5d526be92322121fa74b9f739f01a0`
- `5fa59114413c56f3f0ad7979d928b90b50a36621`

測試使用不存在於正式案例的 `0099`，證明：

- manifest-driven bootstrap 不需新增 Case 白名單；
- 復用 Director capability 不需改 Go 核心；
- action dispatch alias 與 Case ID 無關；
- unsafe/path-like Case ID fail-closed。

### 5. 泛用 durable fanout 已實作

Commits：

- `23e3e3333f6313e536cc0388b0ea1dac47a11f73`
- `9caeee9e4c40a74e4b87164506c7cd15f59a9b12`
- `8b2ea0da7f6858338ca19daf2915c176c16a3e83`
- `ff3a9c8a2cc32bcac813fcf0d7c0d7d756ecd773`
- `f974ec67fa33ab40d27c30f3e355dda03e2e426d`
- `352df6a4edd84520254f2158cda6fff930998e7e`

Step schema 新增資料欄位：

- `fanout_role`
- `fanout_evidence_prefix`

Case 0005 的 030/040 現在只是資料：

- 030 role=`character_master`, prefix=`character`
- 040 role=`scene_concept`, prefix=`scene`

Go fanout planner 不認 Case ID、也不認 030/040；它讀所有同時 READY 的 fanout steps，依 `fanout_role` 從 `visual-assets/requirements.json` 拆 deterministic children。

Fanout runtime：

1. 先完整建立 child plan；
2. 每個 child 用 deterministic work_id 提交同一 `:8848/api/execution/local-work`；
3. 寫 `.openworker/case-fanout-last.json`；
4. 後續 Continue 只讀每個 child terminal state；
5. 任一 child failed → parent FAILED + blocker；
6. 全部 completed → 聚合 `<prefix>_receipts / images / sha256`；
7. parent acceptance 驗證後才標記 SUCCEEDED；
8. 再進入下一 dependency step。

因此 027 approval 後，character / scene children 能真正利用本機 4 slots，而不是因 multiple READY 而中止。

### 6. Case 0005 step 050 已接到泛用 mapper

OpenWorker commit：`652b15a6312e2df8340ffbf661ab3ca9dd291fa4`

go-tool leaf evidence alias fix：`08f4cd8a0fd085a01c2833c4af420b0161bbaccb`

`comfyx-studio.storyboard.real-bind` mapper 不查 `0005-020`，而是：

- 驗證所有直接 dependencies terminal-success；
- 從成功前序 evidence 唯一解析 `storyboard_request`；
- bounded workspace path 驗證；
- 固定輸出 `presentation/storyboard-request.bound.json`。

REAL-bind leaf 先生成所有 `shot_storyboard` 圖，再呼叫 bind handler。其 evidence 現正式提供：

- `shot_image_receipts`
- `shot_images`
- `shot_image_sha256`
- `bound_storyboard_request`

與 Case acceptance 對齊。

## 安全邊界

不把 worklist 內 arbitrary inputs 直接透傳給 executor；Case JSON 不能成為任意 command ingress。

新增 Case 復用既有 capability 時，不改核心；只有新增全新 capability/input contract 時才新增安全 mapper。

GitHub Action 仍只負責安裝/命令 transport，不負責 business execution。

## 尚待泛用化的後續能力

目前已知仍需後續處理：

1. `presentation.openmaic` mapper 需區分 text-only / illustrated presentation contract，不能永遠固定 text-only output。
2. `openworker.case.publish-artifacts` 需改成由 manifest metadata 宣告 artifact evidence keys，才能泛用到 026 / 056 / 090。
3. 060 單一 video fanout 需加入 capability-keyed fanout mapper registry。
4. 070 後 080/082 是兩個 independent READY work，需 generic multi-ready coordinator，而非 visual fanout。
5. 部分 leaf capability 名稱仍帶 `case0005`，應逐步改為 domain capability + manifest parameters。

## 最終架構

`openworker.exe`
→ manifest-driven Case Registry
→ generic dependency / reconciliation engine
→ Action Mapper Registry
→ generic fanout / multi-ready coordinator
→ `:8848` durable queue
→ leaf capability

**Case 是資料；Go Engine 是泛用狀態機。**
