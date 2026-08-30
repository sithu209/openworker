# Case 0003 玉井橋 — UL7 REAL preflight hardening

時間：2026-08-18 15:38 Asia/Taipei

## 目的

把 `scripts/case0003_local_continue_auto.ps1` 收斂成真正可在 UL7 一鍵啟動的 canonical entrypoint。這一批只處理首跑 authority / preflight，不改 acceptance 結果。

## 新增 persistent machine-root authority

OpenWorker `/v1/node/status.inventory.roots` 不再只能依賴 service process environment。

新增 machine root registry：

- env override：`OPENWORKER_MACHINE_ROOTS_FILE`
- Windows default：`%ProgramData%\OpenWorker\machine-roots.json`
- process env 若存在可覆寫 persisted registry
- inventory 只把實際存在的目錄標為 `available=true`

一鍵設定入口：

`scripts/openworker_set_machine_roots.ps1`

持久 authority keys：

- `OPENWORKER_ROOT`
- `GO_TOOL_ROOT`
- `TERRAIN_ROOT`
- `SCENEX_ROOT`
- `ENGINEERING_OS_ROOT`
- `OPENWORKER_REVIEW_DRIVE_ROOT`

## 新增 Case 0003 REAL preflight

`scripts/case0003_local_preflight.ps1`

在任何 business job submission 前 fail-closed 檢查：

1. 實際電腦必須是 `DESKTOP-UL7V2VV`。
2. OpenWorker node machine 必須匹配 UL7。
3. `go / python / powershell` 必須在 inventory 中可用。
4. OpenWorker / go-tool / Terrain / SceneX / Engineering OS roots 必須存在。
5. canonical workspace 必須存在。
6. `.openworker/job-binding.json` 必須是 `openworker.job-binding.v1`，host/workspace/project/job identity 一致且非空。
7. `D:\TaiwanDTM\catalog\dtm_catalog.sqlite` 必須存在且非空。
8. AI-Engineering-OS `/healthz` 必須可連線且不得回 `ok=false`。

成功 receipt：

`workspace\evidence\case0003-local-preflight.json`

schema：`openworker/case0003-local-preflight/v1`

## Canonical auto entrypoint

`scripts/case0003_local_continue_auto.ps1`

現在順序：

```text
resolve machine roots
→ resolve persisted JobBinding OS identity
→ write root-resolution evidence v4
→ Case 0003 REAL preflight
→ canonical v8 physical-gate controller
```

preflight 不通過時不提交任何 business job。

## Acceptance boundary

此批為 code-path / machine-authority hardening；不是 UL7 REAL execution evidence。

目前只有 GEO 可稱 ACCEPTED。Street View / Orthophoto / AOI / Consumer / Blender / SceneX / OS Registry / Review / Delivery 仍需新的 UL7 physical artifacts 與後續 Google Drive connector QC。
