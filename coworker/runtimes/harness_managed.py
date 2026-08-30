"""H7 managed DeepSeek Harness runtime with explicit runtime/engineering job state."""
from __future__ import annotations

import os
from typing import Any, AsyncIterator, Optional

from ..events import Event, EventType
from .harness import DeepSeekHarnessRuntime, HarnessProcessConfig
from .harness_jobs import (
    EngineeringOSJobClient,
    HarnessJobCancellationCoordinator,
    HarnessJobError,
    HarnessRuntimeJobRegistry,
    HarnessRuntimeJobState,
)


class ManagedDeepSeekHarnessRuntime(DeepSeekHarnessRuntime):
    """Harness runtime with one process-local job record per OpenWorker turn."""

    def __init__(self, *, process_config: HarnessProcessConfig | None = None, workspace: str | os.PathLike[str] | None = None, job_registry: HarnessRuntimeJobRegistry | None = None, os_jobs: EngineeringOSJobClient | None = None) -> None:
        super().__init__(process_config=process_config, workspace=workspace)
        self.job_registry = job_registry or HarnessRuntimeJobRegistry()
        self.job_cancellation = HarnessJobCancellationCoordinator(self.job_registry, os_jobs=os_jobs)
        self._current_runtime_job_id: str | None = None

    @staticmethod
    def _engineering_scope(source: Optional[dict[str, Any]]) -> tuple[str | None, str | None]:
        if not isinstance(source, dict):
            return None, None
        os_job_id = source.get("engineering_job_id")
        project_id = source.get("project_id")
        if os_job_id is not None and not isinstance(os_job_id, str):
            raise HarnessJobError("source.engineering_job_id must be a string")
        if project_id is not None and not isinstance(project_id, str):
            raise HarnessJobError("source.project_id must be a string")
        os_job_id = os_job_id.strip() if isinstance(os_job_id, str) else None
        project_id = project_id.strip() if isinstance(project_id, str) else None
        if bool(os_job_id) != bool(project_id):
            raise HarnessJobError("source.engineering_job_id and source.project_id must be supplied together")
        return os_job_id or None, project_id or None

    async def run(self, user_input: str | list, *, source: Optional[dict[str, Any]] = None, display: Optional[str] = None) -> AsyncIterator[Event]:
        session_id = await self._ensure_session()
        os_job_id, project_id = self._engineering_scope(source)
        binding = self.job_registry.begin(session_id=session_id, os_job_id=os_job_id, project_id=project_id)
        self._current_runtime_job_id = binding.runtime_job_id
        interrupted = False
        terminal_emitted = False
        try:
            async for event in super().run(user_input, source=source, display=display):
                if event.type is EventType.TURN_START:
                    data = dict(event.data)
                    data.update({"session_id": session_id, "runtime_job_id": binding.runtime_job_id, "engineering_job_id": os_job_id, "project_id": project_id})
                    yield Event(event.type, data)
                    continue
                if event.type is EventType.INTERRUPTED:
                    interrupted = True
                    final = await self.job_cancellation.cancel_after_runtime_stop(binding.runtime_job_id)
                    data = dict(event.data)
                    data.update({"session_id": session_id, "runtime_job_id": binding.runtime_job_id, "runtime_job_state": final.state.value, "engineering_job_id": os_job_id, "project_id": project_id, "job_detail": final.detail})
                    yield Event(event.type, data)
                    continue
                if event.type is EventType.TURN_END:
                    terminal_emitted = True
                    current = self.job_registry.get(binding.runtime_job_id)
                    if not interrupted and current.state in {HarnessRuntimeJobState.RUNNING, HarnessRuntimeJobState.STOPPING}:
                        current = self.job_registry.fail(binding.runtime_job_id, "Harness turn ended with error") if event.data.get("stop_reason") == "error" else self.job_registry.finish(binding.runtime_job_id)
                    data = dict(event.data)
                    data.update({"session_id": session_id, "runtime_job_id": binding.runtime_job_id, "runtime_job_state": current.state.value, "engineering_job_id": os_job_id, "project_id": project_id, "job_detail": current.detail})
                    yield Event(event.type, data)
                    continue
                yield event
        except Exception as exc:
            current = self.job_registry.get(binding.runtime_job_id)
            if current.state in {HarnessRuntimeJobState.RUNNING, HarnessRuntimeJobState.STOPPING}:
                self.job_registry.fail(binding.runtime_job_id, str(exc))
            raise
        finally:
            if not terminal_emitted:
                current = self.job_registry.get(binding.runtime_job_id)
                if current.state is HarnessRuntimeJobState.RUNNING:
                    self.job_registry.fail(binding.runtime_job_id, "OpenWorker stopped consuming the Harness turn before terminal event")
            self._current_runtime_job_id = None

    def request_interrupt(self) -> None:
        runtime_job_id = self._current_runtime_job_id
        if runtime_job_id is not None:
            current = self.job_registry.get(runtime_job_id)
            if current.state is HarnessRuntimeJobState.RUNNING:
                self.job_registry.mark_stopping(runtime_job_id)
        super().request_interrupt()

    async def health(self) -> dict[str, Any]:
        result = await super().health()
        capabilities = dict(result.get("capabilities", {}))
        capabilities.update({"runtime_job_tracking": True, "engineering_job_cancellation": self.job_cancellation.os_jobs is not None, "cancel_order": "acp-stop-then-os-transition"})
        result["capabilities"] = capabilities
        result["session_id"] = self._session_id
        result["current_runtime_job_id"] = self._current_runtime_job_id
        return result


__all__ = ["ManagedDeepSeekHarnessRuntime"]