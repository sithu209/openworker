# OpenWorker × DeepSeek Harness H6.2 開發進度

更新日期：2026-08-14

狀態：`IMPLEMENTED — DETERMINISTIC OFFICIAL HARNESS TOOL GOLDEN E2E；WIN11 ACTION QUEUED`

## 為什麼需要 H6.2

H6.1 的 plugin-load smoke只能證明：

```text
官方 Cordis loader
→ OpenWorker plugin
→ OS dynamic discovery
→ tool registration
→ ACP initialize/session-new
```

它不能證明模型真的產生 tool call，也不能證明 consequential tool 真的走過 ACP approval。因此 H6.2 新增完整但無付費模型依賴的 agent-loop Golden E2E。

## 使用官方 deterministic LLM Replay

Pinned DeepSeek Harness 已內建：

```text
@deepseek-ai/dsh-llm-replay
```

官方定位就是 keyless snapshot-test LLM replay，可從 recorded `assistant/chunk` 重播模型 stream，包括 tool-call。

因此 H6.2 不寫假 provider，也不直接呼叫 tool `execute()`，而是讓官方 Harness agent loop 自己消費 replay stream。

## Golden E2E 真實鏈

新增：

`tests/runtimes/test_harness_official_engineering_tool_e2e.py`

完整流程：

```text
Python OpenWorker ACP client
→ official dsh-acp-demo composition
→ official @deepseek-ai/dsh-llm-replay
→ first model replay call
→ tool-call: budget__calculate({amount:42})
→ official Harness ToolRuntime
→ OpenWorker Cordis Engineering tool plugin
→ tools/pre-execute
→ localhost context ingress
→ OpenWorker-owned OS dynamic catalog resolves canonical metadata
→ H4 HarnessPermissionBridge
→ OpenWorker PermissionEngine
→ existing approver = ONCE
→ ACP session/request_permission allow-once
→ official ToolRuntime dispatch
→ plugin POST /api/v1/ai/tools/budget.calculate/invoke
→ fake Engineering-OS returns canonical ToolResult
→ ToolRuntime appends tool result
→ second official replay model call
→ assistant committed text DONE
→ ACP prompt returns end_turn
→ tools/result context cleanup
```

這是 agent loop / tool runtime / ACP permission 的真正整鏈，不是直接測 helper function。

## Deterministic replay corpus

測試在 temp workspace 動態建立兩個 model calls：

### Call 1

```text
block-start(tool-call)
block-end(
  id=call-budget-1,
  name=budget__calculate,
  arguments={"amount":42}
)
finish(tool-calls)
```

### Call 2

```text
block-start(text)
block-end(text="DONE")
finish(stop)
```

因此結果完全 deterministic，不依賴真 DeepSeek API、模型抽樣或網路模型服務。

## Fake Engineering-OS 的角色

H6.2 不假裝 fake OS 是真工程計算；它只驗證 agent/runtime transport contract：

```text
GET /api/v1/ai/tools/mcp
POST /api/v1/ai/tools/budget.calculate/invoke
```

Fake OS 嚴格記錄 invoke body，Golden test 要求：

```json
{
  "project_id": "project-h6-2",
  "job_id": "job-h6-2",
  "arguments": {"amount": 42},
  "component_id": "budget-main"
}
```

真 RC / BIM / ComfyX 工程成果驗證仍屬 H8/H9，不在 H6.2 假裝完成。

## Golden assertions

測試必須同時滿足：

1. ACP initialize 成功。
2. ACP session/new 成功。
3. ACP prompt 最終 `end_turn`。
4. committed assistant text 精確等於 `DONE`。
5. OpenWorker approver 只被呼叫一次。
6. approval request tool name = `budget__calculate`。
7. arguments = `{amount:42}`。
8. OpenWorker 自己解析出的 canonical id = `budget.calculate`。
9. fake OS 實際只收到一次 canonical invoke。
10. project/job/component/arguments 正確。
11. context registry 最終清空。
12. OS catalog 至少被 OpenWorker policy side 與 Harness runtime side各發現一次。

## 官方 Harness composition

測試使用 `@deepseek-ai/cordis-plugin-include` include pinned 官方：

```text
examples/acp-agent/cordis.yml
```

只做兩個 composition-level changes：

```text
disable real dsh-llm-deepseek adapter
insert official dsh-llm-replay
insert OpenWorker local Cordis engineering tool plugin
```

ACP、agent loop、ToolRuntime、user-approval、session persistence等都仍是官方 Harness package。

## Win11 Action

Workflow：

```text
OpenWorker Harness H3-H6.2 Official Win11
runs-on: [self-hosted, Windows, X64]
```

最新 Run：

```text
31772905006
OpenWorker ref: 5e386d8ab01a139cca749582f3ad9eb83def96ee
DeepSeek Harness ref: 47f943859bef60e4160492346772ded9b24f765a
status at documentation update: queued
```

新增最後 gate：

```text
H6.2 deterministic official Harness engineering tool Golden E2E
```

在這個 Run 全綠以前，H6.2 只能標 `IMPLEMENTED`，不能標 VERIFIED。

## 下一步

Run `31772905006` 若紅：依真 log 修 plugin / composition / replay corpus，直到全綠。

若綠：

```text
H5 → VERIFIED — WIN11 SESSION BOUNDARY CONTRACT
H6 → VERIFIED — WIN11 DYNAMIC TOOL GATEWAY CONTRACT
H6.1 → VERIFIED — OFFICIAL CORDIS PLUGIN + CONTEXT INGRESS WIN11
H6.2 → VERIFIED — OFFICIAL HARNESS CONSEQUENTIAL TOOL GOLDEN E2E WIN11
```

之後主線進 H7：把 Harness jobs / long-running tool / interrupt / cancel 對到 OpenWorker job UX 與 AI-Engineering-OS job lifecycle。
