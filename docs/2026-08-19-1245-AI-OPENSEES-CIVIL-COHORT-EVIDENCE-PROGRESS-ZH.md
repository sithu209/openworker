# AI-OpenSees Civil Cohort Evidence Closure 進度

時間：2026-08-19 12:45 +08:00

## 本批目標

補齊 AI-OpenSees operator-evidence v0.8 → OpenWorker 最終 acceptance 的 Civil authority cohort 二次驗證。

上一批 AI-OpenSees runtime 已把 active REAL MCT authority 收緊為：同一 source SHA256、同一 Civil version、同一 Civil build，並要求 MATERIAL / SECTION / STATIC_NODAL_LOAD 三類 coverage 完整。本批讓 OpenWorker 不再只信 operator receipt，而是重新讀取 authority-runtime-state.json 並交叉驗證 cohort。

## 已完成

- OpenWorker receipt contract 升級為 `ai-opensees/operator-evidence/v0.8`。
- runtime state contract 升級為 `ai-opensees/mct-authority-runtime-state/v0.5`。
- evidence report 升級為 `openworker/ai-opensees-evidence-report/v0.8`。
- receipt 必須提供且非空：
  - `active_source_civil_version`
  - `active_source_civil_build`
  - `active_source_cohort_valid=true`
- runtime state 必須提供相同三項 cohort evidence。
- OpenWorker fail-closed 驗證：
  - runtime/receipt Civil version 完全一致；
  - runtime/receipt Civil build 完全一致；
  - 任一 cohort valid=false 都拒絕；
  - 任一 version/build 空白都拒絕。
- Regression 新增：
  - cohort valid=false；
  - Civil version 空白；
  - Civil build 空白；
  - runtime Civil version drift；
  - runtime Civil build drift。

## 目前 evidence chain

REAL MCT bytes SHA256
→ active source authority SHA256
→ MATERIAL + SECTION + STATIC_NODAL_LOAD
→ active source Civil version/build cohort
→ runtime-state v0.5
→ operator-evidence v0.8
→ OpenWorker 二次 cross-bind
→ evidence-report v0.8
→ accepted=true（僅在 REAL evidence 全部成立時）

## 尚未宣告

本批是 source-level / validator-level closure，不等同：

- CURRENT HEAD CI PASS；
- REAL Civil 2016 GUI Export authority PASS；
- O87 REAL OpenSees E2E PASS；
- OpenWorker REAL analysis accepted=true。

上述狀態必須有真實 receipt/evidence 才可宣告。