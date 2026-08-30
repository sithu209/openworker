# OpenWorker：AI-OpenSees REAL Solver Execution Evidence 收口

- 日期时间：2026-08-19 12:05（Asia/Taipei）
- Repo：`liuxb99/openworker`
- Branch：`main`

## 1. Evidence report v0.5

OpenWorker AI-OpenSees validator 已升级为：

```text
openworker/ai-opensees-evidence-report/v0.5
```

对应 operator receipt：

```text
ai-opensees/operator-evidence/v0.5
```

## 2. 新增 acceptance gate

必须同时满足：

```text
receipt.solver == OpenSees
receipt.solver_version 非空
receipt.solver_raw_exit_code == 0
analysis.solver == OpenSees
analysis.solver_version 非空
analysis.raw_exit_code == 0
```

并要求 receipt 与 AnalysisResult 三项完全 cross-bind：

```text
solver identity
solver version
raw exit code
```

任何 drift 都不能 `accepted=true`。

## 3. Regression

测试基线同步到 v0.5，并新增负向覆盖：

- receipt solver identity drift；
- empty solver version；
- non-zero solver exit code；
- AnalysisResult / receipt solver version cross-bind drift；
- 保留 REAL MCT bytes tamper；
- 保留 runtime config bytes tamper；
- 保留 OpenSees executable bytes tamper。

## 4. 当前 acceptance chain

```text
REAL Civil MCT bytes
→ authority config bytes
→ fixed authority snapshot SHA256
→ REAL OpenSees.exe bytes
→ solver=OpenSees
→ non-empty solver version
→ raw_exit_code=0
→ AnalysisResult v0.6
→ operator-evidence v0.5
→ OpenWorker evidence-report v0.5
→ accepted=true
```

本文件只记录 source-level closure；REAL Civil 2016 / O87 E2E 仍需真实验收。
