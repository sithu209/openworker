# OpenWorker AI-OpenSees Active Source Authority Evidence 进度

时间：2026-08-19 12:22（Asia/Taipei）

## 本批目标

OpenWorker 最终 `accepted=true` 不能只证明 production catalog 全局拥有 MATERIAL、SECTION、STATIC_NODAL_LOAD；还必须证明这三类 authority 都属于当前 REAL Civil MCT 的同一个 SHA256。

## 已完成

`ValidateAIOpenSeesWorkspace()` 升级为 `openworker/ai-opensees-evidence-report/v0.7`，对应：

- `ai-opensees/operator-evidence/v0.7`
- `ai-opensees/mct-authority-runtime-state/v0.4`

新增最终验收条件：

- receipt `active_source_coverage_valid == true`
- `active_source_sha256` 是合法 SHA256
- `active_source_sha256 == mct_sha256`
- physical REAL MCT bytes SHA256 == `mct_sha256 == active_source_sha256`
- active MATERIAL authority >= 1
- active SECTION authority >= 1
- active STATIC_NODAL_LOAD authority >= 1
- active 三类分类总数 == active source authority count
- runtime active-source SHA/count 与 receipt 完全一致
- AnalysisResult `source_sha256` 与 active-source SHA 完全一致

## Regression

新增负向测试覆盖：

- receipt active source SHA 来自另一份 MCT → reject
- 当前 source 缺 SECTION authority → reject
- runtime active source SHA 与 receipt drift → reject

并保留既有：

- global MATERIAL/SECTION/STATIC_NODAL_LOAD coverage
- runtime/global count drift
- solver identity/version/exit code
- MCT/config/OpenSees.exe physical byte tamper
- artifact hash/path binding

## 解决的问题

旧逻辑可能出现：

MCT-A 有 MATERIAL；MCT-B 有 SECTION；MCT-C 有 STATIC_NODAL_LOAD；catalog 全局三类都有，但当前 MCT-A 并没有完整三类 authority。

v0.7 后此组合无法通过最终 acceptance。

## 边界

本批 regression / validator 代码完成，不等于 REAL AI-OpenSees analysis 已 `accepted=true`。节点升级 receipt 也只能证明 OpenWorker 软件版本已部署，不能替代 REAL Civil 2016 + O87 实机分析证据。
