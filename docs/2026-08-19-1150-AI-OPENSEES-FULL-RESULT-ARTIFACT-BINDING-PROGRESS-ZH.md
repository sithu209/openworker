# OpenWorker：AI-OpenSees 全 Result Artifact Binding 收口

- 日期时间：2026-08-19 11:50（Asia/Taipei）
- Repo：`liuxb99/openworker`
- Branch：`main`
- Capability：`structural.ai_opensees.authority.analyze`
- 固定 REAL 主机：`O87`

## 1. 本批发现的缺口

`openworker/ai-opensees-evidence-report/v0.3` 已经具备：

- operator evidence schema / capability / repository / host gate；
- authority generation / catalog / snapshot digest 三方一致性；
- 10 个 required artifact 的实体路径、SHA256、bytes 重算；
- AnalysisResult v0.6 的部分 artifact hash binding。

但 AnalysisResult ↔ operator artifact 的逐项 binding 原先只覆盖：

```text
analysis-geometry.json
analysis-deformed.obj
analysis-deformation.svg
node_displacements.csv
node_reactions.csv
```

漏掉：

```text
analysis.tcl
opensees.stdout.log
opensees.stderr.log
```

因此 OpenWorker 虽能证明这些实体文件没有相对 operator receipt 被篡改，却还不能证明它们与 `analysis-result.json` 中 solver producer 声明的 hash 一致。

## 2. 本批代码

```text
b6688ed3  fix: bind AI OpenSees report to all result artifact hashes
1f8d1516  test: cover full AI OpenSees result artifact binding
```

`AIOpenSeesAnalysisResult` 新增解析：

```text
script_path / script_sha256
stdout_path / stdout_sha256
stderr_path / stderr_sha256
```

现在 AnalysisResult-backed cross-check 共 8 项：

```text
analysis.tcl
opensees.stdout.log
opensees.stderr.log
analysis-geometry.json
analysis-deformed.obj
analysis-deformation.svg
node_displacements.csv
node_reactions.csv
```

每项都要求：

```text
canonical workspace path 一致
+ AnalysisResult SHA256 合法
+ AnalysisResult SHA256 == operator receipt SHA256
+ operator receipt SHA256 == 实体重新计算 SHA256
```

任何断链均 fail closed，`accepted` 不得为 true。

## 3. Regression

既有 regression 保留：

- valid synthetic evidence 可 accepted；
- authority snapshot drift 必须拒绝；
- SVG 实体篡改必须拒绝。

本批新增：

- 实体 `analysis.tcl` 与 receipt 都保持原样；
- 仅修改 AnalysisResult 内 `script_sha256`；
- 必须出现：

```text
ANALYSIS_ARTIFACT_SHA256_MISMATCH:analysis.tcl
```

从而证明 OpenWorker 不会只信 operator receipt，也不会只信 AnalysisResult。

## 4. 当前验证边界

这些提交是 source + regression contract closure；在真实 CI receipt / REAL O87 execution 出现前，不宣称：

```text
CURRENT HEAD CI PASS
REAL Civil 2016 authority PASS
O87 REAL OpenSees PASS
OpenWorker REAL accepted=true
PRODUCTION READY
```

下一批继续检查 evidence identity / execution identity 是否仍有可由纯软件封口的断点。
