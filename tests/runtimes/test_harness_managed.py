from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

from coworker.events import EventType
from coworker.runtimes.harness import HarnessProcessConfig
from coworker.runtimes.harness_jobs import EngineeringOSJobClient, HarnessRuntimeJobState
from coworker.runtimes.harness_managed import ManagedDeepSeekHarnessRuntime

FIXTURE = Path(__file__).parent / "fixtures" / "mock_acp_server.py"


def _config(tmp_path: Path) -> HarnessProcessConfig:
    return HarnessProcessConfig(
        command=(sys.executable, str(FIXTURE)),
        cwd=tmp_path,
        startup_timeout_s=5.0,
        request_timeout_s=5.0,
    )


@pytest.mark.asyncio
async def test_managed_runtime_emits_runtime_job_identity_and_completes(tmp_path: Path) -> None:
    runtime = ManagedDeepSeekHarnessRuntime(process_config=_config(tmp_path), workspace=tmp_path)
    try:
        events = [event async for event in runtime.run("hello")]
    finally:
        await runtime.aclose()

    assert events[0].type is EventType.TURN_START
    runtime_job_id = events[0].data["runtime_job_id"]
    assert runtime_job_id == "harness-turn-1"
    assert events[-1].data["runtime_job_id"] == runtime_job_id
    assert events[-1].data["runtime_job_state"] == "completed"
    assert runtime.job_registry.get(runtime_job_id).state is HarnessRuntimeJobState.COMPLETED


@pytest.mark.asyncio
async def test_managed_interrupt_waits_for_acp_interrupted_before_os_cancel(tmp_path: Path) -> None:
    order: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            order.append("os-get")
            return httpx.Response(
                200,
                json={
                    "id": "job-1",
                    "project_id": "project-1",
                    "status": "running",
                    "revision": 3,
                    "progress": 20,
                },
            )
        order.append("os-cancel")
        body = json.loads(request.read())
        assert body == {"target": "cancelled", "expected_revision": 3}
        return httpx.Response(
            200,
            json={
                "id": "job-1",
                "project_id": "project-1",
                "status": "cancelled",
                "revision": 4,
                "progress": 20,
            },
        )

    os_jobs = EngineeringOSJobClient(
        "http://engineering-os",
        transport=httpx.MockTransport(handler),
    )
    runtime = ManagedDeepSeekHarnessRuntime(
        process_config=_config(tmp_path),
        workspace=tmp_path,
        os_jobs=os_jobs,
    )
    source = {"engineering_job_id": "job-1", "project_id": "project-1"}
    try:
        async def collect():
            result = []
            async for event in runtime.run("HANG", source=source):
                if event.type is EventType.INTERRUPTED:
                    order.append("openworker-interrupted")
                result.append(event)
            return result

        task = asyncio.create_task(collect())
        for _ in range(100):
            health = await runtime.health()
            if health.get("current_runtime_job_id"):
                break
            await asyncio.sleep(0.01)
        runtime.request_interrupt()
        events = await asyncio.wait_for(task, 5.0)
    finally:
        await runtime.aclose()

    interrupted = next(event for event in events if event.type is EventType.INTERRUPTED)
    assert interrupted.data["runtime_job_state"] == "killed"
    assert interrupted.data["engineering_job_id"] == "job-1"
    assert order[:2] == ["os-get", "os-cancel"]
    # OS transition is completed inside the interrupted-event handling before
    # the event is surfaced to UI/consumers.
    assert order[-1] == "openworker-interrupted"
    assert events[-1].data["runtime_job_state"] == "killed"


@pytest.mark.asyncio
async def test_managed_interrupt_surfaces_failed_os_cancel_in_job_state(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    os_jobs = EngineeringOSJobClient(
        "http://engineering-os",
        transport=httpx.MockTransport(handler),
    )
    runtime = ManagedDeepSeekHarnessRuntime(
        process_config=_config(tmp_path),
        workspace=tmp_path,
        os_jobs=os_jobs,
    )
    source = {"engineering_job_id": "job-1", "project_id": "project-1"}
    try:
        task = asyncio.create_task(
            _collect(runtime, "HANG", source=source)
        )
        for _ in range(100):
            if (await runtime.health()).get("current_runtime_job_id"):
                break
            await asyncio.sleep(0.01)
        runtime.request_interrupt()
        events = await asyncio.wait_for(task, 5.0)
    finally:
        await runtime.aclose()

    interrupted = next(event for event in events if event.type is EventType.INTERRUPTED)
    assert interrupted.data["runtime_job_state"] == "failed"
    assert "OS job cancellation failed" in interrupted.data["job_detail"]
    assert events[-1].data["runtime_job_state"] == "failed"


async def _collect(runtime: ManagedDeepSeekHarnessRuntime, text: str, *, source: dict | None = None):
    return [event async for event in runtime.run(text, source=source)]
