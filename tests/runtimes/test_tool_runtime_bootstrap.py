from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from coworker.runtimes.tool_runtime_bootstrap import (
    ToolRuntimeBootstrapClient,
    ToolRuntimeBootstrapError,
)


def _response(root: Path, *, prompt: str | None = None) -> dict:
    return {
        "session_id": "session-h7",
        "agent": "openworker-harness",
        "project": root.name,
        "goal": "build the deliverable",
        "information_pack": {
            "source": "agent_information_pack",
            "workspace": {
                "workspace_id": "ws-h7",
                "workspace_root": str(root.resolve()),
                "project_name": root.name,
            },
            "engineering_os": {"status": "ready", "selected_tools": ["workspace.publish_artifact"]},
        },
        "prompt": prompt
        or (
            "<AgentInformationPack>\n"
            f"workspace_root={root.resolve()}\n"
            "information_authority=go-tool-runtime\n"
            "execution_authority=AI-Engineering-OS\n"
            "</AgentInformationPack>\n"
            "Task: build the deliverable"
        ),
    }


def test_start_uses_cwd_identity_and_trusts_only_authority_prompt(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("bootstrap\n", encoding="utf-8")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent/start"
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_response(tmp_path))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="http://runtime.test") as http:
        client = ToolRuntimeBootstrapClient("http://runtime.test", client=http)
        out = client.start(tmp_path, "build the deliverable", task="read TASK.md")

    assert seen["workspace_root"] == str(tmp_path.resolve())
    assert seen["project"] == tmp_path.name
    assert seen["agent"] == "openworker-harness"
    assert out.session_id == "session-h7"
    assert out.information_pack["source"] == "agent_information_pack"
    assert "information_authority=go-tool-runtime" in out.prompt
    assert "execution_authority=AI-Engineering-OS" in out.prompt


def test_start_fails_closed_on_workspace_mismatch(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    payload = _response(tmp_path)
    payload["information_pack"]["workspace"]["workspace_root"] = str(other.resolve())
    transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http:
        client = ToolRuntimeBootstrapClient("http://runtime.test", client=http)
        with pytest.raises(ToolRuntimeBootstrapError, match="workspace mismatch"):
            client.start(tmp_path, "work")


def test_start_fails_closed_on_missing_authority_markers(tmp_path: Path) -> None:
    payload = _response(tmp_path, prompt="Task only")
    transport = httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http:
        client = ToolRuntimeBootstrapClient("http://runtime.test", client=http)
        with pytest.raises(ToolRuntimeBootstrapError, match="authority markers"):
            client.start(tmp_path, "work")


def test_start_fails_closed_when_runtime_unavailable(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = ToolRuntimeBootstrapClient("http://runtime.test", client=http)
        with pytest.raises(ToolRuntimeBootstrapError, match="503"):
            client.start(tmp_path, "work")


def test_finish_closes_authority_session() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/agent/finish"
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"session_id": "session-h7", "status": "success"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = ToolRuntimeBootstrapClient("http://runtime.test", client=http)
        client.finish("session-h7", summary="done", result="success")
    assert seen == {"session_id": "session-h7", "summary": "done", "result": "success"}
