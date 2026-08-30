# AI-OpenSees GUI Export Evidence Closure 進度

時間：2026-08-19 12:58 +08:00

## 本批目標

讓 OpenWorker final acceptance 不只驗 Civil 2016 cohort，也獨立驗證 hash-bound runtime state 內的 Civil GUI export provenance。

## 已完成

- 新增 `ai_opensees_gui_export.go`。
- OpenWorker 解析 `authority-runtime-state.json` 時 fail-closed 驗證：
  - active source Civil version 必須明確為 2016；
  - `active_source_exported_at` 非空；
  - `active_source_export_method` 必須包含 MIDAS + EXPORT；
  - `active_source_export_provenance_valid=true`。
- 這項驗證獨立於 producer 的 ready/coverage flag，避免只信 producer 自報狀態。
- runtime-state 本身仍由 operator artifact receipt 的 SHA256/bytes/path 綁定，因此 OpenWorker 驗的是實際 hash-bound runtime evidence。
- regression 已補：
  - 缺 exported_at；
  - 非 authoritative export_method；
  - export provenance flag=false；
  - runtime Civil 2019；
  - 原有 MCT/config/OpenSees.exe tamper coverage 保留。

## Final acceptance chain

REAL MCT bytes SHA256
→ Civil 2016 active-source cohort
→ MIDAS export provenance
→ MATERIAL + SECTION + STATIC_NODAL_LOAD
→ hash-bound runtime-state
→ operator-evidence v0.8
→ OpenWorker evidence-report v0.8
→ accepted=true（僅在 REAL evidence 全部成立時）

## 尚未宣告

本批仍不代表真實 Civil 2016 GUI Export 已完成，也不代表 O87 REAL OpenSees accepted=true。