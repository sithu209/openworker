# OpenWorker × DeepSeek Harness H3 開發進度

更新日期：2026-08-14

狀態：`VERIFIED — OFFICIAL ACP WIN11 LOCAL ACTION`

## H3 結論

H3 已完成 OpenWorker 對官方 DeepSeek Harness ACP 的真 subprocess runtime adapter，並在本機 Windows 11 self-hosted GitHub Action 對 pinned 官方 source composition 完成互通驗證。

固定 upstream：

```text
repo: deepseek-ai/deepseek-harness
commit: 47f943859bef60e4160492346772ded9b24f765a
release family: 0.1.0-rc.5
ACP SDK family: @agentclientprotocol/sdk 0.25.1
pnpm: 11.7.0
```

## 已完成代碼

`coworker/runtimes/harness.py`：

- `HarnessProcessConfig`
- `AcpProcessClient`
- `DeepSeekHarnessRuntime`
- NDJSON JSON-RPC stdio transport
- `initialize`
- `session/new`
- `session/prompt`
- committed `session/update`
- `session/cancel`
- process stderr/exit error mapping
- graceful EOF / terminate / kill shutdown
- unsupported retry/resume/steering/model-switch fail closed

NativeRuntime 仍是產品預設 runtime；H3 驗證通過不代表 H11 default-runtime decision 已完成。

## 永久測試

```text
tests/runtimes/fixtures/mock_acp_server.py
tests/runtimes/test_harness_runtime.py
tests/runtimes/test_harness_official_acp_smoke.py
```

Deterministic subprocess regression 驗證：

```text
spawn
→ initialize
→ session/new
→ session/prompt
→ session/update
→ OpenWorker assistant event
→ session/cancel
→ interrupted event
→ graceful shutdown
```

官方 source smoke 驗證：

```text
OpenWorker Python AcpProcessClient
→ node + tsx
→ pinned official dsh acp-demo composition
→ initialize
→ session/new
→ fresh Harness session
→ graceful shutdown
```

Smoke 不送 prompt，因此不需要真模型 API 呼叫；dummy DeepSeek key 只用於 composition boot。

## Win11 最終證據

Workflow：

```text
AI-Engineering-OS/.github/workflows/openworker-harness-h3-official-win11.yml
runs-on: [self-hosted, Windows, X64]
```

最終證據 Run：

```text
31771872273
OpenWorker ref: 1db845766bd067873cd77e7bf327a196a80368ff
DeepSeek Harness ref: 47f943859bef60e4160492346772ded9b24f765a
conclusion: success
```

全綠 gate：

```text
OpenWorker install                       PASS
compileall                               PASS
H1/H3/H4 Python runtime regressions      PASS
H2 TypeScript contracts                  PASS
official Harness checkout                PASS
exact upstream commit identity           PASS
pnpm official Harness workspace install  PASS
official ACP initialize + session/new    PASS
```

因此 H3 不再是 queued / implemented-only，而是正式 `VERIFIED — OFFICIAL ACP WIN11 LOCAL ACTION`。

## 仍受 upstream ACP 限制

Pinned ACP 官方仍是：

- fresh sessions only
- committed answers only
- 無 durable load/resume/replay
- 無 live reasoning/tool activity/plan/title/usage
- connection-owned lifetime
- 無 per-session close

這些限制由 H5/H6/H7 以 OpenWorker product/runtime boundary 補足或明確 fail closed，不在 H3 假裝存在。
