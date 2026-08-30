# OpenWorker：AI-OpenSees Input Identity Evidence 收口

- 日期时间：2026-08-19 12:00（Asia/Taipei）
- Repo：`liuxb99/openworker`
- Branch：`main`
- Capability：`structural.ai_opensees.authority.analyze`

## 1. 接续点

前一批 OpenWorker 已经做到：

```text
operator-evidence v0.3
→ 10 个 workspace artifact 逐一重新读取
→ bytes / SHA256 / path 验证
→ AnalysisResult 对 TCL / stdout / stderr / geometry / OBJ / SVG / displacement CSV / reaction CSV 做 hash cross-binding
→ REAL MCT 本体重新读取并计算 SHA256
→ commit/run identity 基础 gate
```

本批继续补 input identity。

## 2. Evidence report 升级

OpenWorker evidence report 从：

```text
openworker/ai-opensees-evidence-report/v0.3
```

升级为：

```text
openworker/ai-opensees-evidence-report/v0.4
```

对应接受：

```text
ai-opensees/operator-evidence/v0.4
```

## 3. 新增 operator evidence 字段

OpenWorker 现在读取并要求：

```text
runtime_config_sha256
opensees_executable_sha256
```

两者必须是合法 64 hex SHA256。

## 4. Runtime config 实体 byte binding

OpenWorker 不只相信 receipt 写入的 runtime config hash。

它会直接：

```text
open receipt.runtime_config
→ read REAL file bytes
→ SHA256
→ compare receipt.runtime_config_sha256
```

若实体文件不可读、为空或 hash 漂移，分别 fail-closed。

核心 blocker 包括：

```text
RUNTIME_CONFIG_READ_FAILED
RUNTIME_CONFIG_EMPTY_FILE
RUNTIME_CONFIG_FILE_SHA256_MISMATCH
```

## 5. OpenSees executable 实体 byte binding

同样对：

```text
receipt.opensees_executable
```

直接读取实际 executable bytes 并计算 SHA256。

核心 blocker：

```text
OPENSEES_EXECUTABLE_READ_FAILED
OPENSEES_EXECUTABLE_EMPTY_FILE
OPENSEES_EXECUTABLE_FILE_SHA256_MISMATCH
```

因此 `accepted=true` 不再只表示某个 path 字串曾被声明，而是绑定到实际 binary bytes。

## 6. Source / config / solver path cross-binding

OpenWorker 现在要求：

```text
AnalysisResult.source_path
== receipt.mct_path
```

```text
AnalysisResult.authority_config_path
== receipt.runtime_config
```

```text
runtime-state.config_path
== receipt.runtime_config
```

```text
AnalysisResult.solver_executable
== receipt.opensees_executable
```

path comparison 使用 clean + absolute + Windows case-insensitive 语义。

## 7. 完整 input identity chain

现在 `accepted=true` 前，至少形成：

```text
REAL MCT path
+ REAL MCT SHA256
+ AnalysisResult source path/hash

REAL runtime config path
+ runtime config SHA256
+ runtime-state config path
+ AnalysisResult authority config path
+ catalog root
+ generation
+ authority snapshot SHA256

REAL OpenSees executable path
+ executable SHA256
+ AnalysisResult solver executable path
```

再接既有的 10 个 canonical artifact 实体 hash verification。

## 8. Regression

更新：

```text
go-runtime/internal/evidence/ai_opensees_test.go
```

覆盖：

1. 正常完整 identity evidence 可 accepted；
2. snapshot digest drift 必须拒绝；
3. SVG 实体被篡改必须拒绝；
4. AnalysisResult 宣称的 TCL hash 漂移必须拒绝；
5. REAL MCT bytes 被篡改必须拒绝；
6. runtime config bytes 被篡改必须拒绝；
7. OpenSees executable bytes 被篡改必须拒绝；
8. AnalysisResult authority config path 漂移必须拒绝。

这些 fixture 只验证 validator mechanics，不代表 REAL Civil 2016 / REAL O87 验收。

## 9. 本批提交

```text
a573b1b7  feat: bind AI OpenSees authority config and solver identities
db478c73  test: cover authority config and solver identity binding
```

## 10. 当前边界

本批只封 pure-software evidence contract。

即使 OpenWorker node-upgrade receipt 显示 O87 已安装新版，也不能把 node upgrade 的 `ACCEPTED` 当作：

```text
AI-OpenSees REAL accepted=true
```

最终仍必须取得同一个 REAL analysis workspace 的：

```text
operator-evidence v0.4
analysis-result v0.6
authority-runtime-state v0.2
10 canonical artifacts
REAL Civil 2016 MCT
REAL OpenSees executable
```

并由本 validator 得到：

```text
accepted=true
```
