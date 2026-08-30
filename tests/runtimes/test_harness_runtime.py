from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from coworker.events import EventType
from coworker.runtimes.harness import (
    AcpProcessClient,
    DeepSeekHarnessRuntime,
    HarnessCapabilityError,
    HarnessProcessConfig,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mock_acp_server.py"


def _config(tmp_path: Path) -> HarnessProcessConfig:
    return HarnessProcessConfig(
        command=(sys.executable, str(FIXTURE)),
        cwd=tmp_path,
        startup_timeout_s=5.0,
        request_timeout_s=5.0,
    )


@pytest.mark.asyncio
async def test_acp_process_client_initialize_session_prompt_and_close(tmp_path: Path) -> None:
    updates: list[dict] = []
    client = AcpProcessClient(_config(tmp_path), on_update=updates.append)
    try:
        hello = await client.start()
        assert hello["protocolVersion"] == 1
        session_id = await client.new_session(tmp_path)
        assert session_id
        stop = await client.prompt(session_id, "hello")
        assert stop == "end_turn"
        assert updates[-1]["update"]["content"]["text"] == "ACP:hello"
        assert client.running
    finally:
        await client.close()
    assert not client.running


@pytest.mark.asyncio
async def test_runtime_maps_committed_acp_message_to_openworker_events(tmp_path: Path) -> None:
    runtime = DeepSeekHarnessRuntime(process_config=_config(tmp_path), workspace=tmp_path)
    try:
        events = [event async for event in runtime.run("hello")]
    finally:
        await runtime.aclose()

    assert [event.type for event in events] == [
        EventType.TURN_START,
        EventType.ASSISTANT_MESSAGE,
        EventType.TURN_END,
    ]
    assert events[1].data["content"] == "ACP:hello"
    assert events[-1].data["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_runtime_interrupt_sends_acp_session_cancel(tmp_path: Path) -> None:
    runtime = DeepSeekHarnessRuntime(process_config=_config(tmp_path), workspace=tmp_path)
    try:
        async def collect():
            return [event async for event in runtime.run("HANG")]

        task = asyncio.create_task(collect())
        for _ in range(100):
            if (await runtime.health())["session_created"]:
                break
            await asyncio.sleep(0.01)
        runtime.request_interrupt()
        events = await asyncio.wait_for(task, 5.0)
    finally:
        await runtime.aclose()

    assert EventType.INTERRUPTED in [event.type for event in events]
    assert events[-1].type is EventType.TURN_END
    assert events[-1].data["stop_reason"] == "cancelled"


@pytest.mark.asyncio
async def test_h3_health_reports_only_implemented_capabilities(tmp_path: Path) -> None:
    runtime = DeepSeekHarnessRuntime(process_config=_config(tmp_path), workspace=tmp_path)
    try:
        health = await runtime.health()
    finally:
        await runtime.aclose()
    assert health["capabilities"]["fresh_session"] is True
    assert health["capabilities"]["cancel"] is True
    assert health["capabilities"]["permission_bridge"] is False
    assert health["capabilities"]["resume"] is False
    assert health["capabilities"]["rich_events"] is False


def test_h3_unsupported_runtime_features_fail_closed(tmp_path: Path) -> None:
    runtime = DeepSeekHarnessRuntime(process_config=_config(tmp_path), workspace=tmp_path)
    with pytest.raises(HarnessCapabilityError, match="retry"):
        runtime.retry()
    with pytest.raises(HarnessCapabilityError, match="resume"):
        runtime.resume()
    with pytest.raises(HarnessCapabilityError, match="steering"):
        runtime.queue_steering("later")
    with pytest.raises(HarnessCapabilityError, match="model switching"):
        runtime.switch_model("other")
