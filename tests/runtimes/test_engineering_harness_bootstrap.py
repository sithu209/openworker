from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coworker.events import EventType
from coworker.runtimes.engineering_harness import EngineeringHarnessRuntime
from coworker.runtimes.harness import HarnessProcessConfig
from coworker.runtimes.tool_runtime_bootstrap import (
    ToolRuntimeBootstrap,
    ToolRuntimeBootstrapError,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_acp_server.py"


def _config(tmp_path: Path) -> HarnessProcessConfig:
    return HarnessProcessConfig(
        command=(sys.executable, str(FIXTURE)),
        cwd=tmp_path,
        startup_timeout_s=5.0,
        request_timeout_s=5.0,
    )


class FakeBootstrapClient:
    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.root = root.resolve()
        self.fail = fail
        self.starts: list[tuple] = []
        self.finishes: list[tuple] = []

    def start(self, workspace, goal, *, task="", project="", agent="") -> ToolRuntimeBootstrap:
        self.starts.append((Path(workspace).resolve(), goal, task, project, agent))
        if self.fail:
            raise ToolRuntimeBootstrapError("information authority offline")
        return ToolRuntimeBootstrap(
            session_id="bootstrap-session",
            project=project or self.root.name,
            goal=goal,
            prompt=(
                "<AgentInformationPack>\n"
                f"workspace_root={self.root}\n"
                "information_authority=go-tool-runtime\n"
                "execution_authority=AI-Engineering-OS\n"
                "</AgentInformationPack>\n"
                "Task: authoritative bootstrap"
            ),
            information_pack={"source":"agent_information_pack","workspace":{"workspace_root":str(self.root)}},
        )

    def finish(self, session_id: str, *, summary: str, result: str = "success") -> None:
        self.finishes.append((session_id, summary, result))

    def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_first_turn_injects_authority_prompt_once_and_finishes_session(tmp_path: Path) -> None:
    bootstrap = FakeBootstrapClient(tmp_path)
    runtime = EngineeringHarnessRuntime(
        process_config=_config(tmp_path),
        workspace=tmp_path,
        bootstrap_client=bootstrap,  # type: ignore[arg-type]
    )
    try:
        first = [event async for event in runtime.run("design the bridge")]
        second = [event async for event in runtime.run("continue")]
        health = await runtime.health()
    finally:
        await runtime.aclose()

    first_message = next(event for event in first if event.type is EventType.ASSISTANT_MESSAGE)
    second_message = next(event for event in second if event.type is EventType.ASSISTANT_MESSAGE)
    assert "information_authority=go-tool-runtime" in first_message.data["content"]
    assert "execution_authority=AI-Engineering-OS" in first_message.data["content"]
    assert "<CurrentUserRequest>\ndesign the bridge\n</CurrentUserRequest>" in first_message.data["content"]
    assert "information_authority=go-tool-runtime" not in second_message.data["content"]
    assert second_message.data["content"] == "ACP:continue"
    assert len(bootstrap.starts) == 1
    assert bootstrap.starts[0][0] == tmp_path.resolve()
    assert bootstrap.finishes and bootstrap.finishes[0][0] == "bootstrap-session"
    assert bootstrap.finishes[0][2] == "success"
    assert health["information_authority"] == "go-tool-runtime"
    assert health["execution_authority"] == "AI-Engineering-OS"
    assert health["bootstrap_session_created"] is True


@pytest.mark.asyncio
async def test_bootstrap_failure_fails_closed_before_harness_process_starts(tmp_path: Path) -> None:
    bootstrap = FakeBootstrapClient(tmp_path, fail=True)
    runtime = EngineeringHarnessRuntime(
        process_config=_config(tmp_path),
        workspace=tmp_path,
        bootstrap_client=bootstrap,  # type: ignore[arg-type]
    )
    try:
        events = [event async for event in runtime.run("do work")]
        health = await runtime.health()
    finally:
        await runtime.aclose()

    assert [event.type for event in events] == [EventType.TURN_START, EventType.ERROR, EventType.TURN_END]
    assert events[-1].data["stop_reason"] == "bootstrap_error"
    assert events[1].data["authority"] == "go-tool-runtime"
    assert health["process_running"] is False
    assert len(bootstrap.starts) == 1
    assert bootstrap.finishes == []
