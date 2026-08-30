# Case 0003 — Imagery WorkLedger progress acceptance

更新時間：2026-08-18 Asia/Taipei

## 目的

將「Street View + Orthophoto strict physical gate 已通過」寫入 append-only WorkLedger history，但**不得因此移動 whole-case `accepted_revision_id` / `delivered_revision_id`**。

## 新增 recorder

`scripts/case0003_record_imagery_acceptance.py`

執行前重新驗證：

- current accepted `geo/geolocation.json`；
- Street View manifest `streetview-browser-screenshots/v3`；
- UL7 host；
- 0/90/180/270 四向唯一；
- Google/headless/SwiftShader provenance；
- 四張 PNG physical SHA；
- Orthophoto workspace manifest `orthophoto-workspace/v2`；
- NLSC PHOTO2 z19；
- producer plan lat/lng 與 accepted GEO 一致；
- semantic visibility thresholds；
- Orthophoto JPG physical SHA；
- canonical orthophoto evidence non-empty。

通過後計算一個 imagery fingerprint，綁定：

- GEO SHA；
- Street View manifest SHA；
- 四張 PNG SHA；
- Orthophoto workspace/evidence/JPG SHA。

同 fingerprint 重跑為 idempotent，不會開第二個 progress revision。

## WorkLedger 語意

新建/復用 `kind=progress` revision，goal：`Case 0003 imagery physical acceptance`。

記錄 artifacts：

- accepted GEO；
- Street View manifest；
- 4 張 Street View PNG；
- Orthophoto workspace manifest；
- Orthophoto producer evidence；
- PHOTO2 JPG。

required checks：

1. `Imagery Accepted GEO = passed`
2. `Street View Physical+Semantic QC = passed`
3. `Orthophoto Physical+Semantic QC = passed`

revision 最終狀態只到 `verifying`，reason 明確寫：whole Case acceptance 仍等待 downstream OS/Drive/ChatGPT review。

receipt：

`acceptance/imagery/imagery-acceptance.json`

schema：`openworker-case0003-imagery-acceptance/v1`

status：`IMAGERY_ACCEPTED_PENDING_CASE_COMPLETION`

且 receipt 中：

- `accepted_revision_id = ""`
- `delivered_revision_id = ""`

## Canonical auto controller integration

`case0003_local_continue_auto.ps1` 現在在 v10 controller 完成後讀：

`evidence/case0003-local-continue.json`

只有：

- schema = `openworker/case0003-local-continue/v10`
- `gates_after_submission.streetview = true`
- `gates_after_submission.orthophoto = true`

才會執行 imagery recorder。

因此 job submitted / queued / running 不會被記錄成 acceptance。

## 提交

- imagery recorder：`12d69588ddd1db459d327a31bcd17ed103f385f2`
- auto entrypoint integration：`7779df8513a54f3daa32ae7966465e9e6bbeba50`
- recorder/idempotence/stale-GEO tests：`a22f07c0840069680be4985d34ea93f94cc743fa`

## Acceptance boundary

目前 repo contract 已完成；**尚未有 UL7 fresh imagery，因此目前仍不得宣稱 imagery progress revision 已實際建立。**

下一次 UL7 canonical auto run：

1. strict imagery v10 gates false → 本機並行取得 fresh Street View / PHOTO2；
2. 下一次 reconcile → strict gates true；
3. 自動建立 imagery progress receipt / WorkLedger history；
4. 才允許 downstream Consumer/Blender 依既有 controller gate 往前。
