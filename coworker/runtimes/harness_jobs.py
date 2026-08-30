"""H7 job identity and cancellation bridge for the Harness runtime.

DeepSeek Harness background jobs and AI-Engineering-OS engineering jobs are
separate lifecycle authorities.  This module correlates them without merging
identities: Harness/ACP owns runtime execution cancellation; Engineering-OS
owns the durable engineering job state and Digital Thread.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any
from urllib.parse import quote

import httpx


class HarnessJobError(RuntimeError):
    pass


class EngineeringOSJobError(HarnessJobError):
    pass


class HarnessRuntimeJobState(str, Enum):
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    KILLED = "killed"
    FAILED = "failed"


_OS_CANCELLABLE = frozenset({"draft", "queued", "running", "review"})
_OS_TERMINAL = frozenset({"completed", "published", "cancelled", "archived"})


@dataclass(frozen=True)
class EngineeringOSJobSnapshot:
    id: str
    project_id: str
    status: str
    revision: int
    progress: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EngineeringOSJobSnapshot":
        try:
            job_id = payload["id"]
            project_id = payload["project_id"]
            status = payload["status"]
            revision = payload["revision"]
        except KeyError as exc:
            raise EngineeringOSJobError(f"Engineering-OS job response missing {exc.args[0]}") from exc
        if not isinstance(job_id, str) or not job_id:
            raise EngineeringOSJobError("Engineering-OS job id must be a non-empty string")
        if not isinstance(project_id, str) or not project_id:
            raise EngineeringOSJobError("Engineering-OS project_id must be a non-empty string")
        if not isinstance(status, str) or not status:
            raise EngineeringOSJobError("Engineering-OS job status must be a non-empty string")
        if not isinstance(revision, int) or revision <= 0:
            raise EngineeringOSJobError("Engineering-OS job revision must be a positive integer")
        progress = payload.get("progress", 0)
        if not isinstance(progress, int):
            progress = 0
        return cls(job_id, project_id, status, revision, progress)


class EngineeringOSJobClient:
    """Minimal durable job-control client using the existing public OS API."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout_s,
            transport=self.transport,
        ) as client:
            try:
                response = await client.request(method, path, json=json)
            except httpx.HTTPError as exc:
                raise EngineeringOSJobError(f"Engineering-OS job request failed: {exc}") from exc
        if response.status_code >= 400:
            raise EngineeringOSJobError(
                f"Engineering-OS job request {method} {path} returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise EngineeringOSJobError("Engineering-OS job response was not JSON") from exc
        if not isinstance(payload, dict):
            raise EngineeringOSJobError("Engineering-OS job response must be an object")
        return payload

    async def get(self, job_id: str) -> EngineeringOSJobSnapshot:
        payload = await self._request("GET", f"/api/v1/jobs/{quote(job_id, safe='')}")
        return EngineeringOSJobSnapshot.from_payload(payload)

    async def cancel(self, job_id: str, *, project_id: str | None = None) -> EngineeringOSJobSnapshot:
        """Idempotently transition a cancellable engineering job to cancelled.

        We always read the current revision first because the OS transition API is
        optimistic-concurrency controlled.  Terminal jobs are never rewritten.
        """
        current = await self.get(job_id)
        if project_id is not None and current.project_id != project_id:
            raise EngineeringOSJobError(
                f"Engineering-OS job {job_id} belongs to {current.project_id}, not {project_id}"
            )
        if current.status == "cancelled":
            return current
        if current.status in _OS_TERMINAL:
            raise EngineeringOSJobError(
                f"Engineering-OS job {job_id} is terminal ({current.status}) and cannot be cancelled"
            )
        if current.status not in _OS_CANCELLABLE:
            raise EngineeringOSJobError(
                f"Engineering-OS job {job_id} has unsupported cancellable state {current.status}"
            )
        payload = await self._request(
            "POST",
            f"/api/v1/jobs/{quote(job_id, safe='')}/transitions",
            json={"target": "cancelled", "expected_revision": current.revision},
        )
        cancelled = EngineeringOSJobSnapshot.from_payload(payload)
        if cancelled.status != "cancelled":
            raise EngineeringOSJobError(
                f"Engineering-OS cancel transition returned unexpected state {cancelled.status}"
            )
        return cancelled


@dataclass(frozen=True)
class HarnessRuntimeJobBinding:
    runtime_job_id: str
    session_id: str
    os_job_id: str | None
    project_id: str | None
    state: HarnessRuntimeJobState = HarnessRuntimeJobState.RUNNING
    detail: str | None = None


class HarnessRuntimeJobRegistry:
    """Process-local correlation between one runtime turn and one OS job."""

    def __init__(self) -> None:
        self._bindings: dict[str, HarnessRuntimeJobBinding] = {}
        self._counter = 0

    def begin(
        self,
        *,
        session_id: str,
        os_job_id: str | None = None,
        project_id: str | None = None,
    ) -> HarnessRuntimeJobBinding:
        if not session_id:
            raise HarnessJobError("Harness session id is required")
        if bool(os_job_id) != bool(project_id):
            raise HarnessJobError("OS job_id and project_id must be supplied together")
        self._counter += 1
        runtime_job_id = f"harness-turn-{self._counter}"
        binding = HarnessRuntimeJobBinding(runtime_job_id, session_id, os_job_id, project_id)
        self._bindings[runtime_job_id] = binding
        return binding

    def get(self, runtime_job_id: str) -> HarnessRuntimeJobBinding:
        try:
            return self._bindings[runtime_job_id]
        except KeyError as exc:
            raise HarnessJobError(f"unknown Harness runtime job: {runtime_job_id}") from exc

    def transition(
        self,
        runtime_job_id: str,
        state: HarnessRuntimeJobState,
        *,
        detail: str | None = None,
    ) -> HarnessRuntimeJobBinding:
        current = self.get(runtime_job_id)
        allowed = {
            HarnessRuntimeJobState.RUNNING: {
                HarnessRuntimeJobState.STOPPING,
                HarnessRuntimeJobState.COMPLETED,
                HarnessRuntimeJobState.KILLED,
                HarnessRuntimeJobState.FAILED,
            },
            HarnessRuntimeJobState.STOPPING: {
                HarnessRuntimeJobState.KILLED,
                HarnessRuntimeJobState.COMPLETED,
                HarnessRuntimeJobState.FAILED,
            },
        }
        if current.state == state:
            return current
        if state not in allowed.get(current.state, set()):
            raise HarnessJobError(
                f"invalid Harness runtime job transition {current.state.value} -> {state.value}"
            )
        updated = replace(current, state=state, detail=detail)
        self._bindings[runtime_job_id] = updated
        return updated

    def finish(self, runtime_job_id: str) -> HarnessRuntimeJobBinding:
        return self.transition(runtime_job_id, HarnessRuntimeJobState.COMPLETED)

    def fail(self, runtime_job_id: str, detail: str) -> HarnessRuntimeJobBinding:
        return self.transition(runtime_job_id, HarnessRuntimeJobState.FAILED, detail=detail)

    def mark_stopping(self, runtime_job_id: str) -> HarnessRuntimeJobBinding:
        return self.transition(runtime_job_id, HarnessRuntimeJobState.STOPPING)

    def mark_killed(self, runtime_job_id: str) -> HarnessRuntimeJobBinding:
        return self.transition(runtime_job_id, HarnessRuntimeJobState.KILLED)


class HarnessJobCancellationCoordinator:
    """Coordinate runtime stop acknowledgement with durable OS cancellation."""

    def __init__(
        self,
        registry: HarnessRuntimeJobRegistry,
        *,
        os_jobs: EngineeringOSJobClient | None = None,
    ) -> None:
        self.registry = registry
        self.os_jobs = os_jobs

    async def cancel_after_runtime_stop(self, runtime_job_id: str) -> HarnessRuntimeJobBinding:
        current = self.registry.get(runtime_job_id)
        if current.state == HarnessRuntimeJobState.RUNNING:
            current = self.registry.mark_stopping(runtime_job_id)
        if current.os_job_id is not None:
            if self.os_jobs is None:
                return self.registry.fail(runtime_job_id, "OS job cancellation client is unavailable")
            try:
                await self.os_jobs.cancel(current.os_job_id, project_id=current.project_id)
            except Exception as exc:
                return self.registry.fail(runtime_job_id, f"OS job cancellation failed: {exc}")
        return self.registry.mark_killed(runtime_job_id)


__all__ = [
    "EngineeringOSJobClient",
    "EngineeringOSJobError",
    "EngineeringOSJobSnapshot",
    "HarnessJobCancellationCoordinator",
    "HarnessJobError",
    "HarnessRuntimeJobBinding",
    "HarnessRuntimeJobRegistry",
    "HarnessRuntimeJobState",
]
