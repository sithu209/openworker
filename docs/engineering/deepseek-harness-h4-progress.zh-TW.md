# OpenWorker × DeepSeek Harness H4 開發進度

更新日期：2026-08-14

狀態：`VERIFIED — WIN11 BRIDGE CONTRACT；H6 CANONICAL CONTEXT PRODUCER IMPLEMENTED`

## H4 結論

H4 已把 DeepSeek Harness ACP `session/request_permission` 接回 OpenWorker 既有 PermissionEngine / approver 治理層，且在 Win11 self-hosted Action 通過 subprocess wire regression。

官方 ACP rc.5 permission request 只有：

```text
sessionId
toolCall.toolCallId
```

沒有 `tool_name / arguments / metadata`。因此 H4 不信任 ACP request 本身描述操作，而是要求 OpenWorker-owned canonical context registry：

```text
Harness tool call
→ HarnessToolContextRegistry
→ ACP session/request_permission(call-id only)
→ HarnessPermissionBridge
→ registry.resolve(call-id)
→ PermissionEngine.evaluate(...)
→ existing OpenWorker approver
→ ACP allow-once / reject-once / cancelled
```

找不到 context 一律 `cancelled`。

## 已完成代碼

`coworker/runtimes/harness_permissions.py`：

- `HarnessToolContext`
- `HarnessToolContextRegistry`
- `HarnessPermissionBridge`
- duplicate live call-id fail closed
- hard policy deny 不允許人工 override
- ONCE / DENY 映射
- ALWAYS_TOOL / ALWAYS_COMMAND 由 OpenWorker session policy 持有，不假裝 ACP 有 durable grant

## 永久測試

`tests/runtimes/test_harness_permissions.py` 已覆蓋：

1. registry lifecycle。
2. duplicate call-id fail closed。
3. missing canonical context → cancelled。
4. read auto-allow。
5. interactive approval。
6. DISCUSS hard deny。
7. session allowlist。
8. DENY。
9. 真 ACP subprocess `session/request_permission` wire path。

## Win11 證據

Workflow：

```text
AI-Engineering-OS/.github/workflows/openworker-harness-h3-official-win11.yml
runs-on: [self-hosted, Windows, X64]
```

Run：`31771872273`

結果：`success`

已通過：

```text
H1/H3/H4 runtime regressions              PASS
H2 TypeScript contracts                   PASS
pinned official Harness checkout          PASS
exact upstream commit identity            PASS
official Harness workspace install        PASS
official ACP initialize + session/new     PASS
```

## H6 已補上的缺口

H6 新增 `HarnessEngineeringToolGateway`，會在工程工具提出時用 AI-Engineering-OS 動態 catalog 建立 canonical context，並呼叫：

```text
HarnessToolContextRegistry.register(call-id → exposed tool + args + OS metadata)
```

因此 H4 原本只有 resolver 的安全 seam，現在已有正式 producer。

仍未宣稱「官方 Harness consequential-tool 真實 E2E 完整閉環」，因為 pinned ACP 並不提供動態 tool registration/control plane；後續需要 Harness plugin/tool adapter 把真正的 Harness tool execution 連到 H6 gateway。這個缺口會在 H6/H7 後續 integration gate 明確驗證。
