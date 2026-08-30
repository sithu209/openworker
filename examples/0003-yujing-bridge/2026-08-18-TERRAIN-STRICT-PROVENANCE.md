# Case 0003 — Terrain strict provenance hardening

更新：2026-08-18

## 結論

Case 0003 的 Terrain AOI 不再以「10 個檔案存在 + usable_tiles > 0」作為足夠證據。Canonical local-first 路徑現在要求 Terrain output 與目前 accepted GEO、目前 DTM catalog、實際 build request、10 個 physical artifacts 完整綁定。

## Owning producer

`Terrain_To_DXF/scripts/terrain_aoi_local.ps1`

最新 workspace manifest：`terrain-aoi-workspace/v2`。

v2 新增：

- accepted geolocation lat/lng
- geolocation source path + SHA256
- canonical DTM catalog path + size + SHA256
- AOI build request path + SHA256
- 10 個 required artifact path + size + SHA256
- UL7 host / workspace identity
- usable_tiles

Terrain producer commit：`5e7e8a883985bf8185c44415bcbf50c1490cb4d9`。

## Stale Terrain quarantine

OpenWorker 新增 `scripts/case0003_quarantine_stale_terrain.ps1`。

若現有 `terrain/` 發生任一情況：

- manifest 不是 v2
- host/workspace 不一致
- accepted GEO path/SHA/lat/lng 漂移
- DTM catalog path/size/SHA 漂移
- build request SHA 漂移
- usable_tiles <= 0
- 10 個 artifact 任一 missing/size/SHA/path 不一致

則不刪除歷史成果，而是把整個 `terrain/` 原子移到：

`.openworker/quarantine/terrain/terrain-<timestamp>`

並保存 rejection receipt。OpenWorker commit：`3f1fc4da499355d5fd69de935d0d2dc637e4e0e2`。

Canonical auto entrypoint 在 controller 前執行 Terrain quarantine，因此 stale Terrain 不會先解鎖 SceneX / Consumer。整合 commit：`c197003d064ba45130d0f38a40d56bdeded7d231`。

## Terrain stage WorkLedger history

新增 `scripts/case0003_record_terrain_acceptance.py`。

strict Terrain 成立後，建立/復用 WorkLedger `progress` revision，記錄：

- GEO identity
- catalog identity
- request identity
- Terrain manifest
- 10 個 physical artifacts
- required checks：Terrain Accepted GEO / Terrain Catalog Identity / Terrain Physical Artifact QC

revision 只進 `verifying`，不得呼叫 whole-case `accept_revision()` 或 `deliver_revision()`。

Recorder commit：`e811027e964483e4e7c3e9977abe2c126a418711`。

Canonical auto 整合 commit：`c9c06ca22421841f5512b98f7c841599907eaf19`。

## Regression contract

`tests/test_case0003_terrain_strict_contract.py`

commit：`3194b70fadaeba858e3f5d1108934844798e743d`。

## Acceptance boundary

本批是 IMPLEMENTED，不是 UL7 REAL VERIFIED。Case 0003 整案仍只有 GEO 可以稱為 ACCEPTED；Terrain 必須由 UL7 重新產生 `terrain-aoi-workspace/v2` 與真實 physical artifacts，strict validator 通過後才可稱 Terrain stage accepted。Whole-case ACCEPTED/DELIVERED 仍需下游 Blender/SceneX/OS/Drive/ChatGPT review 完整閉環。
