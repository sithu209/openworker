from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from coworker.engine import ApprovalOutcome
from coworker.permissions import Mode, PermissionEngine
from coworker.runtimes.harness import AcpProcessClient, HarnessProcessConfig
from coworker.runtimes.harness_permissions import (
    HarnessPermissionBridge,
    HarnessToolContext,
    HarnessToolContextRegistry,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_acp_server.py"


def _params(call_id: str = "call-1") -> dict:
    return {"sessionId": "session-1", "toolCall": {"toolCallId": call_id}}


def _config(tmp_path: Path) -> HarnessProcessConfig:
    return HarnessProcessConfig(
        command=(sys.executable, str(FIXTURE)),
        cwd=tmp_path,
        startup_timeout_s=5.0,
        request_timeout_s=5.0,
    )


def test_tool_context_registry_is_authoritative_and_rejects_duplicate_ids() -> None:
    registry = HarnessToolContextRegistry()
    context = HarnessToolContext("call-1", "read_file", {"path": "README.md"})
    registry.register(context)
    assert registry.resolve("call-1") is context
    assert len(registry) == 1
    with pytest.raises(ValueError, match="already registered"):
        registry.register(context)
    assert registry.discard("call-1") is context
    assert registry.resolve("call-1") is None
    assert len(registry) == 0


@pytest.mark.asyncio
async def test_missing_tool_context_fails_closed(tmp_path: Path) -> None:
    async def approver(_request):
        raise AssertionError("approver must not run without canonical tool context")

    bridge = HarnessPermissionBridge(
        permissions=PermissionEngine(tmp_path),
        approver=approver,
        resolve_context=lambda _call_id: None,
    )
    assert await bridge(_params()) == {"outcome": {"outcome": "cancelled"}}


@pytest.mark.asyncio
async def test_read_tool_is_allowed_without_user_prompt(tmp_path: Path) -> None:
    async def approver(_request):
        raise AssertionError("read-only tool must not require approval")

    context = HarnessToolContext("call-1", "read_file", {"path": "README.md"})
    bridge = HarnessPermissionBridge(
        permissions=PermissionEngine(tmp_path),
        approver=approver,
        resolve_context=lambda call_id: context if call_id == context.tool_call_id else None,
    )
    assert await bridge(_params()) == {
        "outcome": {"outcome": "selected", "optionId": "allow-once"}
    }


@pytest.mark.asyncio
async def test_interactive_shell_routes_through_existing_approver(tmp_path: Path) -> None:
    seen = []

    async def approver(request):
        seen.append(request)
        return ApprovalOutcome.ONCE

    context = HarnessToolContext("call-1", "run_shell", {"command": "git status"})
    bridge = HarnessPermissionBridge(
        permissions=PermissionEngine(tmp_path, mode=Mode.INTERACTIVE),
        approver=approver,
        resolve_context=lambda _call_id: context,
    )
    result = await bridge(_params())
    assert result == {"outcome": {"outcome": "selected", "optionId": "allow-once"}}
    assert len(seen) == 1
    assert seen[0].tool_name == "run_shell"
    assert seen[0].arguments == {"command": "git status"}
    assert seen[0].tool_call_id == "call-1"


@pytest.mark.asyncio
async def test_read_only_mode_rejects_consequential_call_without_prompt(tmp_path: Path) -> None:
    async def approver(_request):
        raise AssertionError("hard policy denial must not ask user")

    context = HarnessToolContext("call-1", "run_shell", {"command": "git status"})
    bridge = HarnessPermissionBridge(
        permissions=PermissionEngine(tmp_path, mode=Mode.DISCUSS),
        approver=approver,
        resolve_context=lambda _call_id: context,
    )
    assert await bridge(_params()) == {
        "outcome": {"outcome": "selected", "optionId": "reject-once"}
    }


@pytest.mark.asyncio
async def test_always_command_updates_openworker_session_allowlist(tmp_path: Path) -> None:
    async def approver(_request):
        return ApprovalOutcome.ALWAYS_COMMAND

    permissions = PermissionEngine(tmp_path, mode=Mode.INTERACTIVE)
    context = HarnessToolContext("call-1", "run_shell", {"command": "git status"})
    bridge = HarnessPermissionBridge(
        permissions=permissions,
        approver=approver,
        resolve_context=lambda _call_id: context,
    )
    assert await bridge(_params()) == {
        "outcome": {"outcome": "selected", "optionId": "allow-once"}
    }
    assert "git status" in permissions.session_allow_commands
    assert permissions.evaluate("run_shell", {"command": "git status"}).allowed is True


@pytest.mark.asyncio
async def test_denied_approval_maps_to_reject_once(tmp_path: Path) -> None:
    async def approver(_request):
        return ApprovalOutcome.DENY

    context = HarnessToolContext("call-1", "run_shell", {"command": "git status"})
    bridge = HarnessPermissionBridge(
        permissions=PermissionEngine(tmp_path, mode=Mode.INTERACTIVE),
        approver=approver,
        resolve_context=lambda _call_id: context,
    )
    assert await bridge(_params()) == {
        "outcome": {"outcome": "selected", "optionId": "reject-once"}
    }


@pytest.mark.asyncio
async def test_acp_wire_permission_request_reaches_openworker_bridge(tmp_path: Path) -> None:
    """Prove the real subprocess JSON-RPC request reaches existing OpenWorker approval."""
    seen = []

    async def approver(request):
        seen.append(request)
        return ApprovalOutcome.ONCE

    registry = HarnessToolContextRegistry()
    registry.register(HarnessToolContext("call-1", "run_shell", {"command": "git status"}))
    bridge = HarnessPermissionBridge(
        permissions=PermissionEngine(tmp_path, mode=Mode.INTERACTIVE),
        approver=approver,
        resolve_context=registry.resolve,
    )
    client = AcpProcessClient(_config(tmp_path), on_permission=bridge)
    try:
        await client.start()
        session_id = await client.new_session(tmp_path)
        result = await client.request("mock/request-permission", {"sessionId": session_id})
        assert result == {"ok": True}
        for _ in range(100):
            if seen:
                break
            await asyncio.sleep(0.01)
        assert len(seen) == 1
        assert seen[0].tool_name == "run_shell"
        assert seen[0].tool_call_id == "call-1"
    finally:
        await client.close()
