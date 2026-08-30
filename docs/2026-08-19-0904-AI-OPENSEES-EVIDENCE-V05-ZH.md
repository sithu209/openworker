# OpenWorker：AI-OpenSees Evidence v0.5 验收契约

- 日期时间：2026-08-19 09:04（Asia/Taipei）
- CLI：`openworker-ai-opensees-evidence --workspace <path>`
- Capability：`structural.ai_opensees.authority.analyze`

## 验收目标

OpenWorker 不负责重新求解结构；它负责独立复核工作目录里的 REAL evidence，避免 workflow/self-report 冒充成功。

## 当前结果 schema

```text
ai-opensees/analysis-result/v0.5
```

## 必须验证的关键实体

- assigned hostname = `O87`
- capability id 精确匹配
- source MCT SHA256
- authority runtime generation
- authority catalog root / entry count
- result status = complete
- authority runtime used = true
- operator receipt / runtime state / analysis result 三方 provenance 一致

## 必须 hash-backed 的 artifacts

- `analysis-result.json`
- `analysis-geometry.json`
- `analysis-deformed.obj`
- `analysis-deformation.svg`
- `analysis.tcl`
- `node_displacements.csv`
- `node_reactions.csv`
- `opensees.stdout.log`
- `opensees.stderr.log`
- `authority-runtime-state.json`

对每个 artifact 重新读取实体文件、计算 SHA256、核对 bytes；除 stdout/stderr 允许为空外，其余必须非空。

## SVG 特殊验收

`analysis-deformation.svg` 必须同时满足：

```text
receipt sha256
= workspace file sha256
= analysis-result.deformation_svg_sha256
```

路径字段固定为：

```text
deformation_svg_path
```

任意篡改必须使 `accepted=false`。

## 不能接受的情况

- schema 仍是 v0.4
- capability id 缺省/不匹配
- runtime generation 不一致
- catalog root/entry count 不一致
- source SHA 不一致
- artifact 缺失、大小或 hash 不一致
- result 未使用 authority runtime
- host 不是 O87

只有 `accepted=true` 才能作为 AI-OpenSees REAL Case 的最终证据。
