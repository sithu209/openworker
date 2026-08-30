# AI-OpenSees Civil 2016 Production Gate 進度

時間：2026-08-19 12:50 +08:00

## 本批目標

把「同一 Civil version/build cohort」再收緊為 production acceptance 必須明確屬於 Civil 2016，而不是任意一致版本。

## 已完成

- 新增 OpenWorker 獨立 receipt 解析 gate：`ai_opensees_civil2016.go`。
- `active_source_civil_version` 非空時必須明確包含 `2016`（大小寫不敏感）。
- 允許不同合法字面，例如 `Civil 2016`、`MIDAS Civil 2016`；拒絕 `Civil 2019`、`Civil 2024` 等。
- 空白 version 不在 JSON parser 隱藏，而是保留給主 validator 產生既有 `ACTIVE_SOURCE_CIVIL_VERSION_EMPTY` blocker。
- 新增獨立 regression：
  - Civil 2016 receipt 可解析；
  - Civil 2019 receipt 必須拒絕；
  - 空白 version 仍可進主 validator。

## Evidence 邊界

目前 final acceptance 必須同時滿足：

- REAL MCT bytes SHA256；
- active source SHA256 相同；
- MATERIAL / SECTION / STATIC_NODAL_LOAD coverage；
- Civil version/build cohort 一致；
- Civil version 明確為 2016；
- runtime/operator cross-bind；
- REAL OpenSees executable/hash/version/exit code；
- canonical artifacts 全量 hash 驗證。

## 尚未宣告

本批仍不代表 REAL Civil 2016 GUI Export MCT 已取得，也不代表 O87 REAL analysis accepted=true。真實 GUI export 與實機結果仍需真實 evidence。