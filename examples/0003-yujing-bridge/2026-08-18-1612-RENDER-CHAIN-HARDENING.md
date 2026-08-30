# Case 0003 — Blender / SceneX current-chain hardening

更新時間：2026-08-18 16:12 Asia/Taipei

## 目的

防止 Terrain / Consumer 已重建後，workspace 仍殘留舊 Blender `.blend` / render 或舊 SceneX screenshot，而 controller 因檔案存在與自身 SHA 自洽誤判為 current output。

## Blender

Terrain_To_DXF `scripts/terrain_blender_local.ps1` 現輸出 `blender/blender-workspace.json`，schema `blender-workspace/v2`。

它要求 current `consumer/consumer-workspace.json` = `consumer-workspace/v2`，並綁定：

- `consumer_fingerprint`
- consumer workspace SHA256
- orchestration SHA256
- `.blend` / render / request / evidence / handoff physical SHA256
- `blender_fingerprint`

因此 Consumer 重新生成後，舊 Blender manifest 自動 stale。

Owning repo commit：`a24ffb99c1ab07a97b6707fa48e966c527b80f24`。

## SceneX

SceneX default branch 為 `master`。`scripts/scenex_terrain_real_browse_local.ps1` 現輸出 `scenex-workspace-browse/v2`，要求 current Terrain acceptance 與 `terrain-aoi-workspace/v2`，綁定：

- `terrain_fingerprint`
- terrain workspace manifest SHA256
- current GEO SHA256
- Region Pack / screenshot / evidence SHA256
- active chunks / terrain geometry diagnostics
- `scenex_fingerprint`

Owning repo commit：`8d41fb64548ddd4940631d0a09ad2edc4feb1499`。

## OpenWorker stale quarantine

新增 `scripts/case0003_quarantine_stale_render_outputs.ps1`。

controller 前驗證 Blender / SceneX current upstream identity；任何 mismatch 會將 stage directory 移至 `.openworker/quarantine/<stage>/`，保留 rejection reasons，不直接刪除歷史成果。

commit：`3807322bc8e69db77e59a2706cf2a4b05516a999`。

Canonical auto entrypoint 已在 controller 前依序執行：Imagery → Terrain → Consumer → Render quarantine；root-resolution schema 升 `v10`。

commit：`d6c3a7290eb717f9a4c1a6b9dc8fc7430a19df90`。

## WorkLedger stage history

新增 `scripts/case0003_record_render_acceptance.py`。

只有 Blender v2 + SceneX v2 都與 current upstream fingerprints / physical SHA 一致時才建立或復用 `progress` revision，狀態保持 `verifying`。不呼叫 `accept_revision()` / `deliver_revision()`；whole-case acceptance 仍留給 OS Delivery + Drive / ChatGPT review。

commit：`f81e8658eb702572978ce50c8e745c9b6ce6def2`。

Regression source contract：`5a8ac5948159826dfa05c91a1506cdb0f3645f23`。

## Acceptance boundary

此批為 IMPLEMENTED，尚未在 UL7 產生新的 REAL Blender / SceneX physical outputs。因此不得把 Blender / SceneX 或 whole Case 標成 ACCEPTED。下一次 UL7 reconcile 會自動 quarantine 舊 render chain，重新產生 current-chain outputs，通過後才寫 render progress acceptance。
