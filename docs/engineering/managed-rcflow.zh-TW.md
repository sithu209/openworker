# E6.3 — OS 管理的 RC 柱完整工程流程

## 核心決策

E6.3 不在 OpenWorker 內自行串接 Design Forge、AI-EngSketch 與 AI-BIM-Forge。AI-Engineering-OS 已有正式 `rcflow`，會建立 Job Task、依序執行計算／圖面／BIM、註冊 Artifact，最後將 Job 推進 `review`。

OpenWorker 的責任改成：

```text
Engineering Coworker
→ OpenWorker Approval Gate
→ POST /api/v1/jobs/{id}/flows/rc-column
→ AI-Engineering-OS rcflow
   ├─ design-forge / rc-column
   ├─ engsketch / generate
   └─ aibim / build
→ Calculation + Drawing + IFC Artifacts
→ Job = review
→ E6.2 Review / Approval / Delivery
```

## 輸入契約

依 AI-Engineering-OS `rcflow.ColumnInput`，OpenWorker 對外要求至少：

- job_id
- component_id
- width_mm / depth_mm / clear_height_mm
- concrete_grade / steel_grade
- axial_force_kn / moment_x_knm

並允許 cover、主筋、箍筋與 IFC schema 等 rcflow 已支援欄位。

## 成果契約

OpenWorker 對 rcflow 回應做 fail-closed 驗證：

1. Job ID 必須與請求一致。
2. Job 必須閉合在 `review`。
3. tasks / stages / artifacts 必須為 object list。
4. Artifact 集合必須包含 Drawing 類成果。
5. Artifact 集合必須包含 BIM / IFC 類成果。
6. 所有 OS Artifact 以 E5 `os_artifact_ref()` 納入 Digital Thread，並連回 OS Job。

## Agent Tool

新增：

`engineering_run_rc_column_flow`

它會改變權威工程狀態並執行專業引擎，因此：

- risk_level = high
- requires_approval = true

這個 OpenWorker Approval Gate 只代表「允許 AI 執行此工程流程」，不等同 E6.2 的工程成果 Review approved。

## 與舊 E6 的關係

E6/E6.1 的 direct Design Forge path 保留為低階測試與 specialist integration fixture；正式完整 RC 柱 Golden Path 以 AI-Engineering-OS `rcflow` 為優先，避免 OpenWorker 成為第二套工程 Workflow Engine。
