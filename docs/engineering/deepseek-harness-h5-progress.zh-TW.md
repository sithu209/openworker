# OpenWorker × DeepSeek Harness H5 開發進度

更新日期：2026-08-14

狀態：`IMPLEMENTED — SESSION OWNERSHIP BOUNDARY；WIN11 GATE QUEUED`

## 本批目標

H5 解決 OpenWorker durable conversation 與 DeepSeek Harness runtime session 的所有權問題。重點不是假裝 ACP 已有 resume，而是把目前 pinned upstream 的限制寫進程式契約，避免形成雙重 source of truth 或用危險的 prompt replay 假冒續跑。

## 官方 upstream 結論

Pinned DeepSeek Harness：

```text
47f943859bef60e4160492346772ded9b24f765a
ACP package: @deepseek-ai/dsh-acp
```

官方 ACP README 明確寫出：

- `session/new` 只建立 fresh agent。
- 同一 connection 可有多個 session，且各自有 workspace / cancellation path。
- client disconnect / Cordis disposal 會釋放該 connection 擁有的 sessions。
- Known Limitations：fresh sessions only。
- load / list / resume / delete / fork 都不支援。
- connection-owned lifetime。

因此 H5 不允許把 ACP session id 寫進 OpenWorker durable store 後假裝下次程序可以 resume。

## OpenWorker 現有 durable source of truth

`ConversationStore` 已是產品層持久化來源：

```text
coworker.db
conversations/<conversation-id>.jsonl
```

它持有/恢復：

- OpenWorker `session_id` / conversation identity
- workspace
- model / mode / agent
- append-only messages
- title
- extra roots
- session grants
- compaction state
- pin/archive/origin metadata

H5 保持這個 ownership，不建立第二套 Harness durable transcript database。

## 已完成代碼

新增：

`coworker/runtimes/harness_sessions.py`

### HarnessSessionBinding

只描述：

```text
OpenWorker durable conversation_id
        ↕ process-local mapping
Harness ACP ephemeral session_id
```

state：

```text
UNBOUND
LIVE
LOST
```

### HarnessSessionCoordinator

提供：

- `binding(conversation_id)`
- `bind_live(conversation_id, acp_session_id)`
- `mark_connection_lost()`
- `discard(conversation_id)`
- `require_durable_resume(conversation_id)`
- `capabilities()`

重要安全規則：

1. ACP id 只在 process/connection lifetime 內有效。
2. connection loss 後，所有 live ACP ids 立即失效，OpenWorker conversation identity 不刪除。
3. 同一 OpenWorker conversation 不允許靜默換成另一個 live ACP session。
4. `require_durable_resume()` 明確 fail closed。
5. 禁止把歷史 user prompts 逐條重新送進 fresh ACP session 當成 resume，因為這會重新執行工具與外部副作用。

### capability truth table

目前 pinned ACP：

```text
fresh_session               true
same_connection_multi_turn  true
durable_resume              false
session_load                false
session_list                false
session_delete              false
session_fork                false
transcript_replay           false
```

這些能力是 runtime capability，不會因 OpenWorker 自己有 ConversationStore 就被錯誤標成 Harness 已支援。

## 永久測試

新增：

`tests/runtimes/test_harness_sessions.py`

覆蓋：

1. 未綁定 conversation 不產生假 ACP session。
2. live binding 在同 connection/process 內穩定。
3. conflicting live ACP id 被拒絕。
4. connection loss 清除 ACP ids，但保留 OpenWorker durable conversation identity。
5. durable resume 明確丟出 `HarnessSessionResumeUnsupported`。
6. capability map 不誇大 upstream 能力。

`coworker/runtimes/__init__.py` 已導出 H5 session types。

## Win11 驗證

H5 已加入專用 self-hosted workflow：

```text
AI-Engineering-OS/.github/workflows/openworker-harness-h3-official-win11.yml
name: OpenWorker Harness H3 H4 H5 Official Win11
runs-on: [self-hosted, Windows, X64]
```

最新 H5 Run：

```text
31772077683
OpenWorker ref: 8d9924bdcb34fe654821966e63a5f6d3f54526b7
DeepSeek Harness ref: 47f943859bef60e4160492346772ded9b24f765a
status at documentation update: queued
```

完整 gate 包含：

- compileall
- H1 runtime seam
- H3 ACP adapter regression
- H4 permission bridge + tool context registry
- H5 session ownership tests
- H2 TypeScript contracts
- exact official Harness commit identity
- official Harness workspace install
- official ACP `initialize + session/new` smoke

舊 H4 Run `31771872273` 在本文件更新時仍正在 official Harness workspace install；其前置 H1/H2/H3/H4 gates 已全 PASS。它與 H5 Run 分開記錄，不能把尚未完成的 official ACP smoke 提前標成綠燈。

## H5 沒有做的事

本批刻意沒有：

- 修改 ConversationStore 成 Harness 專屬格式。
- 持久化 ACP session id。
- 用歷史 prompt replay 假裝 durable resume。
- fork/魔改 upstream ACP 來偽造 `session/load`。
- 把 Harness 設成預設 runtime。
- 提前實作 H6 dynamic tools 或 H7 job mapping。

## 下一批 H6

H6 應開始真正的 Tool Gateway：

```text
Harness tool request
→ OpenWorker canonical Tool Gateway
→ HarnessToolContextRegistry.register(call-id, tool_name, arguments, metadata)
→ H4 PermissionBridge
→ OpenWorker PermissionEngine / approver
→ AI-Engineering-OS dynamic tool invocation
→ preserve ToolResult
→ Harness tool result
```

H6 必須優先動態使用 AI-Engineering-OS canonical tool catalog/schema，不複製一套工程工具定義進 Harness。

完成 H6 後，才能做真正 consequential-tool permission E2E，並正式閉環 H4。
