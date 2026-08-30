# OpenWorker：AI-OpenSees Snapshot-bound Evidence v0.6

- 日期时间：2026-08-19 11:08（Asia/Taipei）
- Capability：`structural.ai_opensees.authority.analyze`

## 当前 schema

```text
Runtime state:     ai-opensees/mct-authority-runtime-state/v0.2
Analysis result:   ai-opensees/analysis-result/v0.6
Operator evidence: ai-opensees/operator-evidence/v0.3
OpenWorker report: openworker/ai-opensees-evidence-report/v0.3
```

## 新增 exact authority identity

OpenWorker 现在要求：

```text
receipt.authority_snapshot_sha256
= result.authority_snapshot_sha256
= runtime.snapshot_sha256
```

三者必须都是合法 64 hex SHA256。

`generation + catalog_root + entry_count` 不再足以证明 authority identity。

## Fail-closed blockers

snapshot 不一致会产生：

```text
AUTHORITY_SNAPSHOT_SHA256_INVALID
ANALYSIS_SNAPSHOT_SHA256_MISMATCH
RUNTIME_SNAPSHOT_SHA256_MISMATCH
```

任一 blocker 都必须：

```text
accepted=false
```

## 仍需验证的 artifacts

继续重算 workspace 实体 SHA256：

- analysis-result.json
- analysis-geometry.json
- analysis-deformed.obj
- analysis-deformation.svg
- analysis.tcl
- node_displacements.csv
- node_reactions.csv
- opensees.stdout.log
- opensees.stderr.log
- authority-runtime-state.json

只有 snapshot identity 与实体 artifact evidence 全部通过，才允许 `accepted=true`。
