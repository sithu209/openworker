# OpenWorker AI-OpenSees 必要 Authority 覆盖证据闭环进度

时间：2026-08-19 12:13（Asia/Taipei）

## 本批目标

让 OpenWorker 的最终 `accepted=true` 不再只相信 authority `entry_count`，而是明确要求并二次交叉验证 MATERIAL、SECTION、STATIC_NODAL_LOAD 三类 authority coverage。

## 已完成

### 1. Schema 升级

- operator receipt：`ai-opensees/operator-evidence/v0.6`
- runtime state：`ai-opensees/mct-authority-runtime-state/v0.3`
- OpenWorker evidence report：`openworker/ai-opensees-evidence-report/v0.6`

### 2. Receipt acceptance gates

OpenWorker 现在要求：

- `elastic_material_authority_count >= 1`
- `prismatic_section_authority_count >= 1`
- `static_nodal_load_authority_count >= 1`
- 三项 count 总和必须等于 `authority_entry_count`

### 3. Runtime ↔ receipt 二次交叉绑定

OpenWorker 还会比较 runtime-state 与 operator receipt 的三项 count；任一 drift 都会生成 blocker。

主要 blocker 包括：

- `MATERIAL_AUTHORITY_COVERAGE_MISSING`
- `SECTION_AUTHORITY_COVERAGE_MISSING`
- `STATIC_NODAL_LOAD_AUTHORITY_COVERAGE_MISSING`
- `AUTHORITY_COVERAGE_COUNT_MISMATCH`
- `RUNTIME_MATERIAL_AUTHORITY_COUNT_MISMATCH`
- `RUNTIME_SECTION_AUTHORITY_COUNT_MISMATCH`
- `RUNTIME_STATIC_NODAL_LOAD_AUTHORITY_COUNT_MISMATCH`
- `RUNTIME_AUTHORITY_COVERAGE_COUNT_MISMATCH`

### 4. Regression 补齐

测试基线改成三类 authority 各 1，并新增负向用例：

- MATERIAL 缺失必须拒绝
- SECTION 缺失必须拒绝
- STATIC_NODAL_LOAD 缺失必须拒绝
- runtime/receipt coverage drift 必须拒绝

原有 MCT、runtime config、OpenSees.exe bytes tamper 与 solver identity/version/exit-code regression 继续保留。

## 当前意义

软件 acceptance 已从：

```text
snapshot valid + entry_count
```

提升为：

```text
snapshot valid
+ MATERIAL authority present
+ SECTION authority present
+ STATIC_NODAL_LOAD authority present
+ exact coverage count cross-bind
+ snapshot digest
+ solver/input/artifact evidence
→ accepted=true
```

## 仍未声称 REAL PASS

本批没有产生 REAL Civil 2016 authority，也没有产生 O87 REAL OpenSees 分析 acceptance。只有真正的 Civil 2016 GUI export、真实三类 authority package 与 O87 执行证据完成后，才可以写 REAL `accepted=true`。
