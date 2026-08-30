# Case 0003 玉井橋 — Drive Review Gate Local-First

日期：2026-08-18

## 結論

Case 0003 的最終接受邊界已更正為：

```text
OpenWorker local REAL execution
→ physical artifact gates
→ AI-Engineering-OS Artifact Registry
→ OS Review / Approval
→ OS Delivery Revision
→ OpenWorker fresh mechanical verification
→ immutable review bundle
→ Google Drive review handoff
→ ChatGPT connector-grounded visual / semantic review
→ PASS / TUNE / FAIL
→ PASS only: accept WorkLedger revision
→ bind accepted revision to current OS Delivery + exact Drive publication
→ delivered_revision_id
```

Google Drive 只作為 ChatGPT 審查交換面，不是 business execution transport；OpenWorker / go-tool / owning local tools 仍是 consequential execution authority。

## 舊邏輯缺口

舊 `scripts/case0003_final_acceptance.py` 仍帶有 GitHub-first 時期假設：

1. provenance 寫入歷史 GitHub run IDs；
2. OS delivery path / delivery ID 有舊 hard-code；
3. mechanical checks 全 PASS 後直接 `accept_revision()`；
4. 隨後直接 `deliver_revision()`；
5. Drive / ChatGPT 實體成果審查不是必要 acceptance gate。

此檔只保留歷史遷移參考，**不可作新版 final acceptance authority**。

## Drive review prepare authority

### `scripts/case0003_prepare_drive_review.py`

commit：`6d8bba35e888688359cc71d1b4085638fe148619`

行為：固定 UL7 JobBinding；重新驗 DTM、Terrain、Consumer、Blender、SceneX、OS Delivery；建立 fresh WorkLedger review revision；產出 immutable `openworker-review-bundle/v1`；handoff 到 bounded Google Drive sync root；最後只進 `blocked / WAITING_DRIVE_REVIEW`，**不接受、不交付**。

### `scripts/case0003_local_drive_review_prepare.ps1`

commit：`9a780c79bd3a23f94b58c9481d8ae1bff7714e45`

由 OpenWorker durable local job 執行，固定 UL7、要求正式 OS Delivery receipt、要求明確 `OPENWORKER_REVIEW_DRIVE_ROOT`，同 stage active 時 suppress duplicate，`github_business_transport=false`。

## Connector review apply boundary

### `scripts/case0003_apply_connector_review.py`

2026-08-18 已升級到 schema：

`openworker-case0003-connector-review-apply/v2`

commit：`feab45da30280a51b651f633c9ae6c76e6795d78`

關鍵改動：

- receipt 必須來自 `google-drive-connector`；
- receipt 必須綁定 exact `bundle_manifest_sha256`；
- PASS 必須覆蓋 review request 內全部 immutable artifacts；
- PASS 只呼叫 `accept_revision()`；
- PASS 狀態為 `ACCEPTED_PENDING_FINALIZE`；
- `delivered_revision_id` 強制保持空白；
- TUNE / FAIL / TOOL_GAP 仍由既有 ReviewCycle / review_gap 規則處理。

這避免「ChatGPT 說 PASS」與「OpenWorker 已完成正式 Delivery pointer」被混成同一個動作。

## Reviewed delivery finalizer

### `scripts/case0003_finalize_reviewed_delivery.py`

commit：`9b08ef6ad2828944e155c67cc874cfeffc624ac7`

finalizer 是唯一允許在 connector PASS 後寫 `delivered_revision_id` 的 Case 0003 新 authority。它 fail-closed 驗證：

1. connector apply schema 必須為 v2；
2. verdict 必須為 PASS；
3. status 必須為 `ACCEPTED_PENDING_FINALIZE`；
4. accepted revision 必須就是本次 review revision；
5. local immutable bundle manifest SHA 必須等於 connector receipt / Drive publication 綁定 SHA；
6. Drive publication 必須有 revision folder ID、file ID、ZIP SHA、bundle manifest SHA；
7. OS receipt 必須是 `engineering-os-local-delivery-receipt/v1` 且 `published`；
8. OS delivery manifest / checksum manifest 重新計算 SHA，必須與 receipt 一致；
9. OS delivery manifest 的 delivery ID / project ID / job ID / revision 必須與 receipt 一致；
10. WorkLedger revision 必須已 accepted，且 accepted pointer 必須指向本 revision；
11. 若另一 revision 已成為 delivered pointer，禁止覆寫。

通過後 `revision.delivered` event 寫入的是 **當下真實 identity**：

- OS project/job/delivery ID；
- OS delivery revision；
- manifest/checksum/website SHA；
- Drive revision folder/file ID；
- cloud ZIP SHA；
- exact review bundle manifest SHA。

不再使用舊 GitHub run ID、舊 delivery ID 或寫死 revision=1。

### `scripts/case0003_local_finalize_reviewed_delivery.ps1`

commit：`7a705654eb8f03614609fd1dcff50a36371706b9`

由 OpenWorker durable local job 執行 finalizer；會從最新 connector apply 結果解析 revision ID，同 revision finalizer active 時 suppress duplicate。

## Finalizer regression tests

`tests/test_case0003_reviewed_delivery_finalize.py`

commit：`4b7063cbfc7c524458a3bc0bbb7f1e9bef552378`

覆蓋：

- accepted connector-reviewed revision 可以綁到 current OS Delivery + Drive publication；
- `revision.delivered` event 使用 current OS/Drive identity；
- review bundle bytes 改變後，舊 PASS receipt 立即失效；
- stale bundle 被拒時 `delivered_revision_id` 仍保持空白。

## Controller v6

`case0003_local_continue.ps1`

commit：`6840a73af9e803364894d6e5b4d96672bda84ad0`

schema：`openworker/case0003-local-continue/v6`

現在一鍵 controller 已延伸到完整尾段：

```text
Imagery
→ Terrain AOI
→ SceneX || Consumer → Blender
→ OS Artifact Registry
→ OS Review / Approval
→ OS Delivery
→ Drive review prepare
→ WAITING for ChatGPT connector verdict
→ connector PASS applied
→ reviewed delivery finalizer
→ CASE0003_DELIVERED
```

其中唯一不會被 OpenWorker 自動代替的 quality authority 是：

```text
ChatGPT connector 真正讀 Google Drive revision
→ 檢查實體圖片 / evidence / delivery
→ PASS / TUNE / FAIL / TOOL_GAP
```

這是刻意保留的品質 gate，不是缺口。

## Duplicate-race repair

controller v5：`3cf0870db3b43a3e9dddc87873328de7e1bce03c`

imagery stage-idempotent：`5faba8f6771bc37c10d3d55f85c038cd0f56f749`

controller 會讀 `/v1/jobs?limit=1000`，active stages 不重複提交；imagery submit 也會逐個 Street View / Orthophoto 去重。v6 進一步把 Drive review prepare 與 reviewed-delivery finalize 納入 active-stage suppression。

## Drive 上既有結構

既有 rework revision `rev_0851c5ab49ff459d83ee1cb6268ea8d3` 仍可由 connected Google Drive 找到，含 Blender render、SceneX screenshot/evidence、delivery index、mechanical acceptance、review request / manifest。新版沿用正式 ReviewCycle schema，但 **不繼承舊 revision 的 acceptance**；新的 verdict 必須對本次 UL7 fresh bundle。

## 最終 acceptance rule

Case 0003 現在唯一有效順序：

```text
UL7 REAL artifacts
→ OS registry / approval / delivery
→ fresh mechanical review prepare
→ Drive publication
→ ChatGPT connector physical visual/semantic review
→ apply connector receipt
→ PASS: accepted_revision_id
→ reviewed delivery finalizer
→ delivered_revision_id
```

TUNE 必須建立受 allowlist 限制的 tuning revision；FAIL / TOOL_GAP 必須回 owning repo 修正並 REAL rerun。**任何 mechanical success、OpenWorker job success、OS publish success，都不能單獨使 Case 0003 最終 ACCEPTED/DELIVERED。**
