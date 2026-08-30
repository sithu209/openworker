# Case 0003 玉井橋 — Drive Review Return Local-First

日期：2026-08-18

## 本輪補掉的最後 transport contract 缺口

新版 Case 0003 已不再以 GitHub Actions 作 Google Drive business publication。但前一版 review contract 仍殘留舊 API publish identity：`drive_file_id + cloud_zip_sha256`，而 local-first `ReviewCycle.handoff_to_drive_sync()` 只同步 revision folder，沒有單一 immutable ZIP。結果會出現：ChatGPT 已在 Drive 看得到成果，但 connector PASS receipt 無法滿足舊 transport identity。

本輪改為：

```text
OpenWorker local controller
→ fresh mechanical review revision
→ immutable review bundle folder
→ deterministic immutable <revision_id>.zip
→ Google Drive Desktop bounded sync root
→ ChatGPT Google Drive connector reads revision folder + ZIP
→ connector recomputes ZIP SHA and observes Drive folder/file IDs
→ connector-review-receipt.json
→ Drive Desktop sync returns receipt to UL7
→ OpenWorker local apply
→ PASS => accepted_revision_id only
→ reviewed-delivery finalizer
→ delivered_revision_id
```

## 新 canonical schema

- Drive prepare：`openworker-case0003-drive-review-prepare/v2`
- connector review apply：`openworker-case0003-connector-review-apply/v3`
- reviewed delivery finalize：`openworker-case0003-reviewed-delivery-finalize/v2`
- local continuation controller：`openworker/case0003-local-continue/v8`

## Immutable ZIP seal

新增 `scripts/case0003_seal_drive_review.py`。

規則：

- ZIP 只包含 immutable review bundle 內容；
- entry 排序固定；
- ZIP timestamp 固定，讓相同 bundle 產生穩定 bytes；
- 本機 ZIP 與 Drive sync ZIP 重新計算 SHA256，必須完全一致；
- prepare receipt 記錄 `review_zip_path`、`review_zip_sha256`、`drive_sync_zip_target`；
- Drive cloud folder/file ID 不由本機猜測，必須由 Google Drive connector 實際觀察。

主要 commits：

- ZIP seal：`681eaae2e4c12726e91f75d54f42f68c725a4c74`
- durable prepare + seal：`e4d765486337537a8c831df986133851e8ebe6f3`
- connector apply v3：`a3487fac0fbaa186077c0a3a1795120145f7e2d6`
- finalizer v2：`7dbeab20f2cd6c6ece16402406609d765a8c5662`

## Review receipt return channel

新增 `scripts/case0003_local_apply_drive_review.ps1`。

每個 Drive-synced revision folder 的 canonical return inbox 為：

`connector-review-receipt.json`

OpenWorker 只在下列條件全部成立時提交 apply job：

- `transport == google-drive-connector`；
- receipt `revision_id` == current prepared revision；
- receipt bundle manifest SHA == local immutable bundle manifest SHA；
- cloud `drive_revision_folder_id` 非空；
- cloud `drive_zip_file_id` 非空；
- connector-reviewed ZIP SHA == local immutable ZIP SHA；
- cloud bundle manifest SHA == local bundle manifest SHA。

不滿足任何一項就 fail-closed，不接受舊 receipt、不接受另一個 revision 的 PASS。

commit：`0d47db4de5ff0a05ae7b1052ae5bf69e284e7d5e`

## Controller v8

`case0003_local_continue.ps1` 現在新增 `drive_receipt` gate 與 `review_apply` active-stage suppression：

```text
Drive review prepared
→ receipt 未同步：CHATGPT_GOOGLE_DRIVE_CONNECTOR_REVIEW_REQUIRED
→ receipt 已同步：OpenWorker 自動提交 connector review apply
→ PASS：自動提交 reviewed-delivery finalizer
→ finalizer PASS：CASE0003_DELIVERED
```

commit：`ddc3a0c56173e171dc30bb39a9c68ba5b172f17c`

## 舊 GitHub-first publication workflow

`.github/workflows/case-0003-drive-api-publish-ul7.yml` 未再作 business transport。為保留 migration provenance，檔案保留，但已改為 manual-only 且立即 fail，明確標示 retired；沒有 push trigger、沒有 UL7 self-hosted business job、沒有 Drive access token publication。

commit：`3d93003c7a9952c7ef4c84c2d1be9dfe1b528360`

對應 regression test 已改為要求 retired workflow + local-first ZIP/return loop：`df8c4b1c71723a8980d7173f8969986576bf26d3`。

## Acceptance boundary

這些提交只代表 orchestration contract 已補齊，仍不代表 UL7 REAL 已跑通。

Case 0003 仍只有 GEO 可稱 ACCEPTED。Street View / Orthophoto / AOI / Consumer / Blender / SceneX / OS Registry / OS Approval / Delivery / Drive review 都必須由 UL7 fresh physical artifacts 與 connector-grounded review 實際通過後才能更新 acceptance。
