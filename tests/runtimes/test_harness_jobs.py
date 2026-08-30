from __future__ import annotations

import httpx
import pytest

from coworker.runtimes.harness_jobs import (
    EngineeringOSJobClient,
    EngineeringOSJobError,
    HarnessJobCancellationCoordinator,
    HarnessJobError,
    HarnessRuntimeJobRegistry,
    HarnessRuntimeJobState,
)


def _job(status: str = "running", revision: int = 4) -> dict:
    return {
        "id": "job-1",
        "project_id": "project-1",
        "status": status,
        "revision": revision,
        "progress": 25,
    }


@pytest.mark.asyncio
async def test_os_job_cancel_uses_current_revision_and_transition_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=_job())
        assert request.url.path == "/api/v1/jobs/job-1/transitions"
        assert request.read().decode() == '{"target":"cancelled","expected_revision":4}'
        return httpx.Response(200, json=_job("cancelled", 5))

    client = EngineeringOSJobClient(
        "http://engineering-os",
        transport=httpx.MockTransport(handler),
    )
    result = await client.cancel("job-1", project_id="project-1")
    assert result.status == "cancelled"
    assert result.revision == 5
    assert [request.method for request in requests] == ["GET", "POST"]


@pytest.mark.asyncio
async def test_os_job_cancel_is_idempotent_when_already_cancelled() -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_job("cancelled", 7))

    client = EngineeringOSJobClient("http://engineering-os", transport=httpx.MockTransport(handler))
    result = await client.cancel("job-1", project_id="project-1")
    assert result.status == "cancelled"
    assert calls == 1


@pytest.mark.asyncio
async def test_os_job_cancel_never_rewrites_completed_job() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_job("completed", 9))

    client = EngineeringOSJobClient("http://engineering-os", transport=httpx.MockTransport(handler))
    with pytest.raises(EngineeringOSJobError, match="terminal"):
        await client.cancel("job-1", project_id="project-1")


@pytest.mark.asyncio
async def test_os_job_project_identity_is_verified() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_job())

    client = EngineeringOSJobClient("http://engineering-os", transport=httpx.MockTransport(handler))
    with pytest.raises(EngineeringOSJobError, match="belongs to"):
        await client.cancel("job-1", project_id="project-other")


def test_runtime_job_registry_keeps_harness_and_os_ids_separate() -> None:
    registry = HarnessRuntimeJobRegistry()
    binding = registry.begin(session_id="acp-session", os_job_id="job-1", project_id="project-1")
    assert binding.runtime_job_id == "harness-turn-1"
    assert binding.session_id == "acp-session"
    assert binding.os_job_id == "job-1"
    assert binding.state is HarnessRuntimeJobState.RUNNING
    registry.mark_stopping(binding.runtime_job_id)
    assert registry.get(binding.runtime_job_id).state is HarnessRuntimeJobState.STOPPING
    registry.mark_killed(binding.runtime_job_id)
    assert registry.get(binding.runtime_job_id).state is HarnessRuntimeJobState.KILLED


def test_runtime_job_registry_rejects_partial_os_scope_and_invalid_transition() -> None:
    registry = HarnessRuntimeJobRegistry()
    with pytest.raises(HarnessJobError, match="supplied together"):
        registry.begin(session_id="acp-session", os_job_id="job-1")
    binding = registry.begin(session_id="acp-session")
    registry.finish(binding.runtime_job_id)
    with pytest.raises(HarnessJobError, match="invalid"):
        registry.mark_stopping(binding.runtime_job_id)


@pytest.mark.asyncio
async def test_cancel_coordinator_cancels_durable_os_job_only_after_runtime_stopping() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_job())
        return httpx.Response(200, json=_job("cancelled", 5))

    registry = HarnessRuntimeJobRegistry()
    binding = registry.begin(session_id="acp-session", os_job_id="job-1", project_id="project-1")
    client = EngineeringOSJobClient("http://engineering-os", transport=httpx.MockTransport(handler))
    coordinator = HarnessJobCancellationCoordinator(registry, os_jobs=client)
    final = await coordinator.cancel_after_runtime_stop(binding.runtime_job_id)
    assert final.state is HarnessRuntimeJobState.KILLED


@pytest.mark.asyncio
async def test_cancel_coordinator_fails_closed_when_os_cancel_cannot_be_confirmed() -> None:
    registry = HarnessRuntimeJobRegistry()
    binding = registry.begin(session_id="acp-session", os_job_id="job-1", project_id="project-1")
    coordinator = HarnessJobCancellationCoordinator(registry)
    final = await coordinator.cancel_after_runtime_stop(binding.runtime_job_id)
    assert final.state is HarnessRuntimeJobState.FAILED
    assert "unavailable" in (final.detail or "")
