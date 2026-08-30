# ChatGPT → OpenCode Remote Bridge 缺口

時間：2026-08-19 09:45 +08:00

## 目標

在不使用 GitHub Actions 作為 Case 業務橋樑的前提下，補上：

`ChatGPT -> Remote MCP -> ODA OpenCode Server -> openworkerctl -> 127.0.0.1:8848 -> OpenWorker 本機總控`

OpenCode 官方提供 `opencode serve` headless HTTP server，預設 localhost:4096，並有 session / shell API；因此 Remote Bridge 不需要讓 ChatGPT 直接碰 ODA shell，也不需要讓模型自行拼任意 REST。

## 安全邊界

Remote MCP 只暴露四個固定工具：

- `supervisor_status`
- `case_status`
- `case_continue`
- `queue_clear`

其中 `case_continue` 目前只允許 Case 0005；`queue_clear` 只允許本機電腦；任何任意 shell、任意 URL、任意 capability、任意 Case payload 都禁止。

Remote MCP 本身不直接執行 Action，而是呼叫 ODA 本機 OpenCode server 的固定 shell endpoint，shell command 只能是 `%ProgramData%\OpenWorker\bin\openworkerctl.exe` allowlist 命令。

## 遠端連線方式

MCP server 本身只監聽 localhost。若要讓 ChatGPT 遠端連線，應使用受控 MCP tunnel / private tunnel，而不是把 OpenCode 4096 或 go-tool 8848 直接公開到 Internet。

Remote MCP 必須有 bearer token；OpenCode server 必須有 Basic Auth password。

## Product 限制

代碼層可以完整補上 Remote MCP bridge；但 ChatGPT 帳號是否能在目前產品層直接掛載具有 write/modify 能力的自訂 MCP，取決於 ChatGPT 當前方案與 developer-mode 可用性。這是產品權限，不應偽裝成 OpenWorker 代碼問題。

因此驗收拆成兩層：

1. **Code closure**：ODA 本機 `opencode serve` + `openworker-opencode-mcp` + `openworkerctl` 可形成完整 allowlisted chain。
2. **ChatGPT REAL closure**：當 ChatGPT 端能掛載該 Remote MCP 後，實際呼叫 `case_continue`，看到 ODA ledger 進展與 Drive PPTX。
