# OpenWorker × DeepSeek Harness H6.1 開發進度

更新日期：2026-08-14

狀態：`IMPLEMENTED — CORDIS TOOL PLUGIN + LOCAL CONTEXT INGRESS；WIN11 OFFICIAL PLUGIN SMOKE QUEUED`

## 本批目標

H6 已完成 OpenWorker-side AI-Engineering-OS dynamic tool gateway，但真正的 DeepSeek Harness agent 還需要在 Harness runtime 裡看到並執行這些工具。H6.1 使用官方 Cordis / `ctx.tools` extension point完成這個缺口，不 fork Harness，也不修改 ACP wire。

正式鏈：

```text
AI-Engineering-OS /api/v1/ai/tools/mcp
→ OpenWorker EngineeringOSToolClient（policy-side authority）
→ official Harness Cordis plugin（runtime-side adapter）
→ ctx.tools.register(ToolDefinition)
→ model tool call
→ tools/pre-execute
→ localhost OpenWorker call-context ingress
→ HarnessToolContextRegistry
→ H4 PermissionBridge
→ official user-approval
→ ACP session/request_permission(callId)
→ OpenWorker approver
→ Harness tool execute
→ OS /api/v1/ai/tools/{canonical_id}/invoke
→ OS ToolResult
→ tools/result cleanup
```

## 官方 Harness extension point

Pinned upstream：

```text
deepseek-ai/deepseek-harness
47f943859bef60e4160492346772ded9b24f765a
```

官方 API 已確認：

```text
ctx.tools.register(ToolDefinition)
```

且：

```text
ToolDefinition extends ToolSchema
ToolSchema.parameters = Record<string, unknown>
```

因此 AI-Engineering-OS `/tools/mcp` 回傳的 raw `inputSchema` 可以直接作為 Harness tool `parameters`，不需要複製或翻譯成另一套工程 schema。

官方 policy seam：

```text
tools/pre-execute
→ allow / deny / ask
→ ctx.approval
```

所以 consequential permission 也走 Harness 官方工具 pipeline。

## 已完成：OpenWorker localhost context ingress

新增：

`coworker/runtimes/harness_context_ingress.py`

### `HarnessContextIngressServer`

安全限制：

- 只 bind `127.0.0.1`。
- 預設產生高 entropy Bearer token。
- POST body 上限預設 1 MiB。
- 只接受：

```json
{
  "callId": "...",
  "name": "...",
  "arguments": {}
}
```

- 多任何 `canonical_tool_id / side_effect / requires_approval` 等欄位都拒絕。
- plugin 不能自己宣稱某工具是 read 或 mutate。
- OpenWorker 以 `HarnessEngineeringToolGateway.prepare_call()` 重新從自己的 OS dynamic catalog 解析 canonical metadata。
- unknown tool / duplicate live call-id fail closed。
- authenticated DELETE 可在 tool result 後清除 context。

這個 side-channel 只補 ACP rc.5 permission payload 缺少 tool name/args 的資訊，不修改 ACP protocol。

## 已完成：官方 Cordis Engineering Tool Plugin

新增：

`harness/upstream-plugin/openworker-engineering-tools.ts`

Plugin：

1. `inject = ['tools']`，依官方 Cordis lifecycle 等待 ToolRuntime。
2. `GET /api/v1/ai/tools/mcp` 動態發現 OS tools。
3. 驗證 exposed name、raw inputSchema、canonical annotation、duplicate name/id。
4. 每個 OS tool 使用：

```text
ctx.tools.register(ToolDefinition)
```

5. raw OS `inputSchema` 原樣成為 `ToolDefinition.parameters`。
6. tool output 保留 OS extensible ToolResult JSON，不建立第二套結果格式。
7. `read / compute` side-effect 直接交給既有 pipeline。
8. `mutate / publish / unknown` 在 `tools/pre-execute`：
   - 先 POST `callId + name + arguments` 到 OpenWorker ingress。
   - registration 失敗就直接 throw/fail closed，不進 approval。
   - registration 成功後回 `{kind:'ask'}`。
9. official user-approval 再產生 ACP `session/request_permission(callId)`。
10. tool execution 使用 canonical OS `/invoke` endpoint 並 forward `exec.signal` 到 fetch。
11. `tools/result` 對已登記 call-id 做 best-effort DELETE cleanup。

## 設定來源

Plugin 可由 Cordis config 或 deployment env 提供：

```text
OPENWORKER_ENGINEERING_OS_BASE_URL
OPENWORKER_ENGINEERING_OS_TOKEN
OPENWORKER_HARNESS_CONTEXT_URL
OPENWORKER_HARNESS_CONTEXT_TOKEN
OPENWORKER_ENGINEERING_PROJECT_ID
OPENWORKER_ENGINEERING_JOB_ID
OPENWORKER_ENGINEERING_COMPONENT_ID
OPENWORKER_ENGINEERING_ALLOW_PUBLISH
```

測試 smoke 使用 env，避免修改 upstream ACP composition 的既有 config contract。

## 永久測試

新增：

`tests/runtimes/test_harness_context_ingress.py`

覆蓋：

- authenticated context registration。
- canonical metadata 由 OpenWorker OS catalog 解析。
- missing auth 拒絕。
- policy field smuggling 拒絕。
- unknown tool 拒絕。
- duplicate live call-id 拒絕且不覆寫原 context。
- DELETE cleanup。

新增：

`tests/runtimes/test_harness_official_tool_plugin_smoke.py`

它使用 pinned 官方 Harness source composition：

```text
official examples/acp-agent/cordis.yml
+ one ordinary local Cordis plugin row
→ openworker-engineering-tools.ts
```

並啟動 local fake Engineering-OS `/api/v1/ai/tools/mcp`，驗證：

```text
official Cordis loader
→ local OpenWorker plugin loaded
→ plugin dynamic OS discovery actually happened
→ tools registered without breaking composition
→ ACP initialize
→ ACP session/new
```

不送 model prompt，因此這個 smoke 不假裝是完整 model→tool E2E。

## Win11 Action

Workflow 已擴充為：

```text
OpenWorker Harness H3 H4 H5 H6 H6.1 Official Win11
runs-on: [self-hosted, Windows, X64]
```

最新 Run：

```text
31772772677
OpenWorker ref: 087c4a7fa22977057fc0ab3ac223fd4246a78a54
DeepSeek Harness ref: 47f943859bef60e4160492346772ded9b24f765a
status at documentation update: queued
```

Gate 新增：

```text
H6.1 localhost context ingress regression
official Harness Cordis Engineering tool plugin smoke
```

並保留 H1-H6、H2 contract、exact pin、official ACP smoke 全部回歸。

## 尚未宣稱完成的最後一層

H6.1 目前已把 runtime plugin / context side-channel 寫好，但尚未宣稱以下 full E2E 已完成：

```text
real model produces Engineering-OS tool call
→ official Harness executes tool
→ mutate tool triggers ACP approval
→ OpenWorker user approves
→ real local AI-Engineering-OS invocation
→ real ToolResult returns to model
```

這條需要下一個 Golden E2E 使用可控模型/fixture 或真模型，不能用「直接呼叫 plugin execute」冒充 model loop。

## 下一批

1. 先收 Run `31772772677`，修到 official plugin smoke 全綠。
2. 增加 H6.2 consequential-tool Golden E2E：最好使用 deterministic provider fixture 驅動真正 Harness loop 產生 tool call，避免付費模型造成非決定性。
3. H6.2 閉環後進 H7 jobs/interrupt/cancellation mapping。
