# OpenWorker × DeepSeek Harness H6 開發進度

更新日期：2026-08-14

狀態：`IMPLEMENTED — WIN11 H1/H3/H4/H5/H6 REGRESSION PASS；OFFICIAL GATE IN PROGRESS`

## 本批目標

H6 建立 OpenWorker 與 AI-Engineering-OS 之間的動態工程工具 gateway，不在 Harness 或 OpenWorker 複製第二套工程 schema / recipe authority。

正式資料流：

```text
AI-Engineering-OS canonical registry
→ GET /api/v1/ai/tools/mcp
→ OpenWorker EngineeringOSToolClient.discover()
→ HarnessEngineeringToolGateway
→ model tool schema
→ Harness tool call id + arguments
→ HarnessToolContextRegistry.register(...)
→ H4 PermissionBridge / PermissionEngine / approver
→ POST /api/v1/ai/tools/{canonical_id}/invoke
→ preserve OS ToolResult
→ cleanup call context
```

## AI-Engineering-OS 真實 contract

OS `registerAgentNativeRoutes()` 建立 canonical tool registry，並公開：

```text
GET  /api/v1/ai/tools/mcp
GET  /api/v1/ai/tools
GET  /api/v1/ai/tools/{id}
POST /api/v1/ai/tools/{id}/invoke
GET  /api/v1/ai/capabilities
GET  /api/v1/ai/recipes
POST /api/v1/ai/recipes/{id}/execute
POST /api/v1/ai/execute
```

H6 使用 `/tools/mcp` 作為模型工具發現來源，因為它直接帶：

```text
name
inputSchema
annotations.canonical_tool_id
annotations.side_effect
annotations.requires_job_scope
annotations.cost_class
```

OS 自己將 canonical dotted tool id 轉成 MCP-safe 名稱，例如：

```text
bridge.export_site_gltf
→ bridge__export_site_gltf
```

OpenWorker 不反向猜 dotted id，而是只相信 annotation 的 `canonical_tool_id`。

真正 invoke contract：

```json
{
  "project_id": "...",
  "job_id": "...",
  "component_id": "...",
  "arguments": {},
  "allow_publish": false
}
```

## 已完成代碼

新增：

`coworker/runtimes/harness_engineering_tools.py`

### `EngineeringOSToolClient`

- `GET /api/v1/ai/tools/mcp` 動態 discovery。
- 可選 Bearer token。
- 不接受沒有 `canonical_tool_id` 的 tool。
- 不接受 duplicate exposed name / canonical id。
- 不接受非法 inputSchema。
- `POST /api/v1/ai/tools/{canonical_id}/invoke`。
- job-scoped tool 缺 project/job 時 fail closed。
- HTTP/JSON/non-object response 轉成明確 gateway error。

### `EngineeringOSTool`

保留：

- exposed MCP-safe name
- canonical OS tool id
- description
- input schema
- permission metadata

並可輸出 OpenAI function schema，讓模型使用 OS 當下的最新 schema。

### `EngineeringOSToolMetadata`

OpenWorker 保留 OS annotation 作為 policy context：

```text
canonical_tool_id
side_effect
requires_job_scope
cost_class
```

Permission mapping：

```text
read / compute → 不因 OS side-effect 類型額外要求 approval
mutate / publish / unknown consequential class → requires_approval=True
```

未知 side-effect 採 fail-safe，不靜默當 read。

### `HarnessEngineeringToolGateway`

- `refresh()`：重新讀 OS dynamic catalog。
- `model_schemas()`：提供模型 schema。
- `resolve_tool()`：只允許已 discovery 的 exposed name。
- `prepare_call()`：H4 canonical context producer。
- `invoke_prepared()`：只允許已 prepare 的 call。
- `finish_call()`：清除 context。
- invoke 無論成功或失敗都以 finally 清掉 context，避免 stale permission context。

## H4 真正 producer 已補上

H4 原本只有：

```text
call-id → resolve canonical context
```

H6 現在正式負責：

```text
prepare_call(call-id, exposed-name, arguments)
→ resolve OS dynamic tool
→ build HarnessToolContext
→ registry.register(...)
```

因此 permission request 不再需要相信 ACP payload 裡不存在的 tool name/args。

## 永久測試

新增：

`tests/runtimes/test_harness_engineering_tools.py`

使用 `httpx.MockTransport` 驗證：

1. dynamic MCP discovery 保留 canonical OS authority。
2. OpenAI model schema 直接來自 OS inputSchema。
3. mutate side-effect 會變成 OpenWorker approval requirement。
4. 缺 canonical annotation fail closed。
5. `prepare_call()` 真正寫入 H4 `HarnessToolContextRegistry`。
6. mutating OS tool 經 H4 PermissionBridge / existing approver。
7. prepared call 使用 canonical dotted id 呼叫 OS invoke endpoint。
8. project/job/component/arguments body 正確。
9. OS ToolResult dict 不被重新發明成另一套 result contract。
10. 成功/失敗都清除 call context。
11. job-scoped tool 缺 project/job fail closed。

## Win11 本機 Action

專用 workflow：

```text
OpenWorker Harness H3 H4 H5 H6 Official Win11
runs-on: [self-hosted, Windows, X64]
```

Run：

```text
31772297067
OpenWorker ref: 162104f1510094d5c702e86c83c607cf08ee7ff4
DeepSeek Harness ref: 47f943859bef60e4160492346772ded9b24f765a
```

目前已取得本機 runner，以下已 PASS：

```text
OpenWorker checkout/install                  PASS
compileall                                   PASS
H1/H3/H4/H5/H6 Python runtime regressions    PASS
H2 TypeScript contracts                      PASS
```

目前 Action 正繼續執行：

```text
pinned official Harness checkout
exact upstream identity
pnpm official workspace install
official ACP initialize + session/new
```

因此 H6 已不是 queued，但在最後 official gate 完成前仍不標 VERIFIED。

## 已確認的 H3/H4 前置證據

Run `31771872273` 已完整 `success`，包含：

```text
H1/H3/H4 regression PASS
H2 contract PASS
exact pinned Harness checkout PASS
pnpm official workspace install PASS
official ACP initialize + session/new PASS
```

因此 H3 已正式 `VERIFIED — OFFICIAL ACP WIN11 LOCAL ACTION`；H4 bridge contract 也有 Win11 證據。

## H6.1 upstream extension point 研究結果

Pinned 官方 Harness 已確認有正式工具 extension seam：

```text
ctx.tools.register(ToolDefinition)
```

`ToolDefinition.parameters` 本身就是 raw JSON Schema；因此 OS `/tools/mcp` 的 `inputSchema` 可以原樣成為 Harness tool parameters，不必轉成另一套工程 schema。

官方工具 policy seam：

```text
tools/pre-execute
→ allow / deny / ask
→ user-approval
→ ACP session/request_permission
```

所以 H6.1 不需要 fork ACP protocol。

但 ACP permission request 仍只有 call-id。真正 consequential tool E2E 還需要一條 OpenWorker-owned side-channel：Harness plugin 在回 `ask` 之前，先把：

```text
callId
exposed tool name
arguments
OS canonical annotations
```

送回 OpenWorker，先填入 `HarnessToolContextRegistry`；之後 ACP `session/request_permission(callId)` 才能安全被 H4 判斷。

這條 side-channel 是 OpenWorker/Harness plugin integration，不修改 ACP wire contract。

## 下一批 H6.1

```text
AI-Engineering-OS dynamic catalog
→ official Harness local Cordis plugin
→ ctx.tools.register(raw OS inputSchema)
→ tools/pre-execute
→ OpenWorker call-context side-channel
→ H4 PermissionBridge
→ ACP approval
→ real OS invoke
→ Harness tool result
```

H6.1 完成後再進 H7 runtime jobs / interrupt mapping 與 H8 RC Golden Job Native vs Harness A/B。
