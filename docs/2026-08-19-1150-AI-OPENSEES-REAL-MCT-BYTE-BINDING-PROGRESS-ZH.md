# OpenWorker：AI-OpenSees REAL MCT Byte Binding 收口

- 日期时间：2026-08-19 11:50（Asia/Taipei）
- Repo：`liuxb99/openworker`
- Branch：`main`
- Capability：`structural.ai_opensees.authority.analyze`

## 1. 本批发现的证据身份缺口

此前 OpenWorker 会检查：

```text
operator-evidence.mct_sha256
== analysis-result.source_sha256
```

但这只证明两个 JSON 对同一个 hash 声明一致。

若两个 JSON 同时写入同一个错误/伪造 hash，而 OpenWorker 不重新读取 `operator-evidence.mct_path` 对 MCT 本体重算 SHA256，则 `accepted=true` 仍没有真正绑定到 REAL Civil GUI Export MCT 的实体 bytes。

## 2. 本批代码

```text
a81dd253  fix: bind accepted evidence to REAL MCT bytes and run identity
a0dc872d  test: require REAL MCT byte binding for AI OpenSees evidence
```

OpenWorker validator 现在要求：

```text
receipt.mct_path 非空
→ 实体文件可读取
→ bytes > 0
→ 对实体重新计算 SHA256
→ actual MCT SHA256 == receipt.mct_sha256
→ receipt.mct_sha256 == analysis-result.source_sha256
```

因此证据链变成：

```text
REAL MCT bytes
↕ SHA256
operator-evidence.mct_sha256
↕ equality
analysis-result.source_sha256
```

任一断链均 fail closed。

新增 blocker：

```text
MCT_PATH_EMPTY
MCT_READ_FAILED:<error>
MCT_EMPTY
MCT_FILE_SHA256_MISMATCH
```

## 3. Execution identity 同步加固

同批补上 operator receipt 基础 execution identity gate：

```text
commit_sha 必须为 40 或 64 位 hex Git object id
run_id 必须为正整数
run_attempt 必须为正整数
runtime_config 不得为空
opensees_executable 不得为空
```

对应 blocker：

```text
COMMIT_SHA_INVALID
RUN_ID_INVALID
RUN_ATTEMPT_INVALID
RUNTIME_CONFIG_EMPTY
OPENSEES_EXECUTABLE_EMPTY
```

这些检查不能替代 GitHub 服务端 provenance，但可阻止空值/格式错误 receipt 被 OpenWorker 接受。

## 4. Regression

validator regression 现在真实建立测试 MCT 文件，并让 receipt 指向该实体路径。

新增负向测试：

1. valid workspace 先能 accepted；
2. 保持 receipt / AnalysisResult 声明不变；
3. 篡改 MCT 文件 bytes；
4. validator 必须拒绝；
5. 必须出现：

```text
MCT_FILE_SHA256_MISMATCH
```

## 5. 当前软件闭环状态

截至本批，OpenWorker 对 AI-OpenSees REAL acceptance 已能独立重验：

- capability / repository / O87 host；
- run identity 基础格式；
- REAL MCT 实体 bytes；
- authority generation/catalog/snapshot digest；
- 10 个 required artifacts 的路径/bytes/SHA256；
- 8 个 AnalysisResult-backed artifacts 的 producer hash ↔ receipt hash ↔ 实体 hash；
- AnalysisResult v0.6 / runtime-state v0.2 / operator-evidence v0.3。

## 6. 仍未宣称

没有真实 receipt 就仍不能写：

```text
CURRENT HEAD CI PASS
REAL Civil 2016 GUI Export MCT PASS
REAL MATERIAL authority PASS
REAL SECTION authority PASS
REAL STATIC_NODAL_LOAD authority PASS
O87 REAL OpenSees E2E PASS
OpenWorker REAL accepted=true
PRODUCTION READY
```

下一步继续做 source-level 最后审计；若没有新的纯软件 blocker，就把边界正式收敛为只剩 REAL Civil 2016 / O87 实机验收。
