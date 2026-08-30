from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_openworkerctl_is_inside_existing_go_runtime():
    assert (ROOT / "go-runtime" / "go.mod").is_file()
    assert (ROOT / "go-runtime" / "cmd" / "openworkerctl" / "main.go").is_file()


def test_mcp_bridge_is_narrow_and_local_first():
    src = text("go-runtime/cmd/openworker-opencode-mcp/main.go")
    assert 'const supportedProtocol = "2025-06-18"' in src
    assert 'openCodeURL:"http://127.0.0.1:4096"' in src
    assert '"supervisor_status"' in src
    assert '"case_status"' in src
    assert '"case_continue"' in src
    assert '"queue_clear"' in src
    assert 'DESKTOP-ODAQN0D' in src
    assert 'validOrigin' in src
    assert '/session/"+sid+"/shell' in src
    assert 'quotePS(b.ctl)' in src
    assert 'tool %q is not allowlisted' in src


def test_secure_tunnel_is_outbound_only_and_secret_safe():
    src = text("scripts/start-openworker-secure-mcp-tunnel.ps1")
    assert "http://127.0.0.1:8850/mcp" in src
    assert "127.0.0.1:8851" in src
    assert "CONTROL_PLANE_API_KEY" in src
    assert "MCP_EXTRA_HEADERS='Authorization: env:OPENWORKER_MCP_AUTH'" in src
    assert "MCP_DISCOVERY_EXTRA_HEADERS='Authorization: env:OPENWORKER_MCP_AUTH'" in src
    assert "secrets_present_in_argv=$false" in src
    assert "0.0.0.0" not in src
    assert "github" not in src.lower()


def test_tunnel_client_is_pinned_and_built_from_official_source():
    src = text("scripts/install-openai-secure-mcp-tunnel-client.ps1")
    assert "https://github.com/openai/tunnel-client.git" in src
    assert "[string]$Version = 'v0.0.10'" in src
    assert "checkout --detach $Version" in src
    assert "go.Source build" in src
    assert "built_from_source=$true" in src


def test_one_shot_activation_never_uses_github_actions_and_binds_case_ledger():
    src = text("scripts/activate-case0005-secure-mcp-remote.ps1")
    assert "activate-case0005-local-supervisor.ps1" in src
    assert "install-openworker-opencode-bridge.ps1" in src
    assert "start-openworker-opencode-bridge.ps1" in src
    assert "verify-openworker-opencode-bridge.ps1" in src
    assert "install-openai-secure-mcp-tunnel-client.ps1" in src
    assert "start-openworker-secure-mcp-tunnel.ps1" in src
    assert "verify-openworker-secure-mcp-tunnel.ps1" in src
    assert "REMOTE_TRANSPORT_READY" in src
    assert "LOCAL_VERIFIED" in src
    assert "TUNNEL_VERIFIED" in src
    assert "secure-mcp-remote-activation.json" in src
    assert "case-supervisor-ledger.jsonl" in src
    assert "remote_transport_ready" in src
    assert "AppendAllText" in src
    assert "workflow_dispatch" not in src
    assert "gh workflow" not in src.lower()
