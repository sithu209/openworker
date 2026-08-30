# OpenWorker Harness Integration

狀態：H2 `VERIFIED — WIN11 LOCAL ACTION`；H3 process adapter `IMPLEMENTED — OFFICIAL ACP WIN11 ACTION QUEUED`。

這個目錄是 OpenWorker 對 DeepSeek Harness 的整合層，不是 DeepSeek Harness upstream 的 vendor copy，也不是第二套 OpenWorker UI。

## 固定架構原則

1. DeepSeek Harness upstream 固定到 commit `47f943859bef60e4160492346772ded9b24f765a` / `0.1.0-rc.5`。
2. 第一優先復用官方 `@deepseek-ai/dsh-acp` 的 Agent Client Protocol JSON-RPC stdio 控制面。
3. ACP 只被視為 bootstrap/control transport，不被誤稱為完整 OpenWorker Runtime bridge。
4. OpenWorker 仍保留 `NativeRuntime` 為預設；H3 完成 process adapter 也不會提前切換預設 runtime。
5. OpenWorker Permission/Approval 與 AI-Engineering-OS 工程權威邊界不變。
6. 不直接修改 DeepSeek Harness core；缺口優先由 OpenWorker profile/plugin 補齊。

## ACP rc.5 已能提供

- fresh agent session；
- text prompt；
- committed assistant text；
- `session/cancel`；
- one-shot permission request/decision；
- 一個 stdio connection 管理多個 session。

## ACP rc.5 尚未提供 OpenWorker 所需的完整能力

- durable load/resume/replay；
- live reasoning / token delta；
- live tool activity / tool cards；
- plan/title/usage stream；
- per-session close；
- additional directories / MCP server injection；
- image/audio/embedded resource prompt。

因此 H3/H4/H5 不會單純把 ACP 等同完整 `DeepSeekHarnessRuntime`。目標形態仍是：

```text
OpenWorker DeepSeekHarnessRuntime
        │
        ├─ ACP stdio
        │    ├─ initialize
        │    ├─ session/new
        │    ├─ session/prompt
        │    ├─ session/cancel
        │    └─ one-shot permission control
        │
        └─ OpenWorker Harness plugins / gateway
             ├─ live session/event bridge
             ├─ tool gateway bridge
             ├─ approval bridge
             └─ durable session/resume bridge
```

## H2 contract files

- `upstream-lock.json`：upstream commit/release/package pin。
- `src/protocol.ts`：transport capability contract；所有 ACP 缺口都必須顯式為 `false`。
- `src/health.ts`：版本與 health/capability report。
- `tests/contracts.test.mjs`：永久測試，防止未實作能力被誤宣稱為 supported。

## H3 process adapter

H3 新增 Python runtime 邊界：

```text
coworker/runtimes/harness.py
```

核心元件：

- `HarnessProcessConfig`：明確 sidecar command / cwd / env / timeout；不猜 upstream 安裝路徑。
- `AcpProcessClient`：以 `asyncio.create_subprocess_exec()` 啟動真 subprocess，stdin/stdout 使用官方 NDJSON JSON-RPC framing。
- `DeepSeekHarnessRuntime`：將 ACP fresh-session / prompt / committed assistant message / cancel 映射回既有 OpenWorker `Event/EventType`。
- `health()`：只回報已實作能力，H4 permission bridge、H5 resume、rich events 仍為 false。
- `aclose()`：stdin EOF → graceful process exit；超時後 terminate/kill，避免 orphan sidecar。

正式啟動時由 `OPENWORKER_HARNESS_COMMAND` 指定 Harness ACP process；Windows 建議用 JSON string array，避免 command-line quoting 漂移，例如：

```text
["node","path\\to\\deepseek-harness\\packages\\examples\\acp-demo\\lib\\bin.js","--config","path\\to\\cordis.yml"]
```

H3 不把固定本機路徑寫入 OpenWorker，也不把 DeepSeek API key 寫進 repo。

### H3 權限策略

ACP 收到 `session/request_permission` 時，H3 **fail closed** 回 `cancelled`。這是故意的：正式 one-shot allow/reject 必須等 H4 接到 OpenWorker `PermissionEngine` / approval UX，不能由 H3 偷渡自動允許。

### H3 session 策略

H3 只建立 fresh session，並在 runtime instance 內重用該 session。`retry()`、`resume()`、steering、runtime model switch 會顯式丟 `HarnessCapabilityError`，不做假相容。 durable resume/replay 留到 H5。

## H3 官方互通 smoke

新增：

```text
tests/runtimes/test_harness_official_acp_smoke.py
```

此測試不使用 mock ACP server，而是由 Win11 Action checkout exact upstream commit，安裝官方 workspace，然後由 OpenWorker Python `AcpProcessClient` 啟動：

```text
node --import tsx
packages/examples/acp-demo/src/bin.ts
--config examples/acp-agent/cordis.yml
```

並依官方 zero-build source launcher 設：

```text
TSX_TSCONFIG_PATH=<deepseek-harness>/tsconfig.json
```

驗證流程：

```text
OpenWorker Python client
→ official DeepSeek Harness process
→ initialize
→ protocol version negotiation
→ session/new
→ official Harness session/agent factory
→ graceful shutdown
```

不送 prompt，因此不發生真模型 API 呼叫；`DEEPSEEK_API_KEY` 只使用 dummy boot value。

## 驗證

H2 TypeScript contract：

```cmd
cd harness
npm install
npm test
```

H3 deterministic Python ACP process regression：

```cmd
python -m pytest tests/runtimes/test_harness_runtime.py -q
```

H3 official interoperability smoke：

```cmd
set DSH_HARNESS_ROOT=<pinned deepseek-harness checkout>
python -m pytest tests/runtimes/test_harness_official_acp_smoke.py -q -rs
```

專用 Windows 11 self-hosted workflow：

```text
AI-Engineering-OS/.github/workflows/openworker-harness-h3-official-win11.yml
Run: 31767728540
runs-on: [self-hosted, Windows, X64]
OpenWorker ref: 1870dfbf87dd598c361f5b63b7fdaa158adcef52
Harness ref: 47f943859bef60e4160492346772ded9b24f765a
```

該 workflow 只在自身修改或手動 dispatch 時觸發，不再被 AI-Engineering-OS 的其他 main push 反覆取消。Run `31767728540` 已建立，目前 queued；在它完成前不宣稱 H3 已 VERIFIED。
