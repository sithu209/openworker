"""Engineering Harness runtime composed from existing OpenWorker seams.

The unified H7 runtime keeps each authority separate:
* go-tool-runtime owns Project Workspace information/bootstrap;
* AI-Engineering-OS owns durable project/job/tool execution state;
* ManagedDeepSeekHarnessRuntime owns per-turn runtime-job correlation/cancellation;
* OpenWorker owns permission decisions;
* DeepSeek Harness owns ACP/model execution.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from ..events import Event, EventType
from .harness import HarnessProcessConfig, PermissionHandler
from .harness_jobs import EngineeringOSJobClient, HarnessRuntimeJobRegistry
from .harness_managed import ManagedDeepSeekHarnessRuntime
from .tool_runtime_bootstrap import (
    ToolRuntimeBootstrap,
    ToolRuntimeBootstrapClient,
    ToolRuntimeBootstrapError,
)


class EngineeringHarnessRuntime(ManagedDeepSeekHarnessRuntime):
    """Managed Harness runtime with authoritative Project Workspace bootstrap."""

    def __init__(
        self,
        *,
        process_config: HarnessProcessConfig | None = None,
        workspace: str | os.PathLike[str] | None = None,
        bootstrap_client: ToolRuntimeBootstrapClient | None = None,
        bootstrap_project: str = "",
        initial_bootstrap: ToolRuntimeBootstrap | None = None,
        permission_handler: PermissionHandler | None = None,
        job_registry: HarnessRuntimeJobRegistry | None = None,
        os_jobs: EngineeringOSJobClient | None = None,
    ) -> None:
        resolved_process = process_config or HarnessProcessConfig.from_env(cwd=workspace)
        env = dict(resolved_process.env)
        if os_jobs is None:
            base_url = str(env.get("OPENWORKER_ENGINEERING_OS_BASE_URL") or "").strip()
            if base_url:
                os_jobs = EngineeringOSJobClient(
                    base_url,
                    token=str(env.get("OPENWORKER_ENGINEERING_OS_TOKEN") or "").strip() or None,
                )
        super().__init__(
            process_config=resolved_process,
            workspace=workspace,
            job_registry=job_registry,
            os_jobs=os_jobs,
        )
        self._permission_bridge_enabled = permission_handler is not None
        if permission_handler is not None:
            self._client._on_permission = permission_handler
        self._bootstrap_client = bootstrap_client or ToolRuntimeBootstrapClient.from_env()
        self._owns_bootstrap_client = bootstrap_client is None
        self._bootstrap_project = str(bootstrap_project or "").strip()
        self._engineering_job_id = str(env.get("OPENWORKER_ENGINEERING_JOB_ID") or "").strip()
        self._bootstrap: ToolRuntimeBootstrap | None = initial_bootstrap
        self._bootstrap_injected = False
        self._bootstrap_lock = asyncio.Lock()
        self._last_result = "success"
        self._last_summary = "OpenWorker engineering Harness session closed"

    @property
    def bootstrap(self) -> ToolRuntimeBootstrap | None:
        return self._bootstrap

    async def _bootstrap_prompt(self, user_input: str) -> str:
        if self._bootstrap is None:
            async with self._bootstrap_lock:
                if self._bootstrap is None:
                    self._bootstrap = await asyncio.to_thread(
                        self._bootstrap_client.start,
                        self.workspace,
                        user_input,
                        task="Execute the current Project Workspace task using dynamically discovered engineering tools.",
                        project=self._bootstrap_project,
                        agent="openworker-harness",
                    )
        assert self._bootstrap is not None
        self._bootstrap_injected = True
        return (
            self._bootstrap.prompt.rstrip()
            + "\n\n<CurrentUserRequest>\n"
            + user_input
            + "\n</CurrentUserRequest>"
        )

    def _scoped_source(self, source: Optional[dict[str, Any]]) -> dict[str, Any]:
        scoped = dict(source or {})
        if self._bootstrap_project and self._engineering_job_id:
            existing_project = scoped.get("project_id")
            existing_job = scoped.get("engineering_job_id")
            if existing_project not in (None, "", self._bootstrap_project):
                raise ValueError("source.project_id conflicts with engineering host scope")
            if existing_job not in (None, "", self._engineering_job_id):
                raise ValueError("source.engineering_job_id conflicts with engineering host scope")
            scoped["project_id"] = self._bootstrap_project
            scoped["engineering_job_id"] = self._engineering_job_id
        return scoped

    async def run(
        self,
        user_input: str | list,
        *,
        source: Optional[dict[str, Any]] = None,
        display: Optional[str] = None,
    ) -> AsyncIterator[Event]:
        if not isinstance(user_input, str):
            async for event in super().run(user_input, source=self._scoped_source(source), display=display):
                yield event
            return
        try:
            prompt = await self._bootstrap_prompt(user_input) if not self._bootstrap_injected else user_input
        except ToolRuntimeBootstrapError as exc:
            self._last_result = "failed"
            self._last_summary = f"go-tool-runtime bootstrap failed: {exc}"
            yield Event(EventType.TURN_START, {"runtime": "harness", "source": source, "display": display})
            yield Event(EventType.ERROR, {"runtime": "harness", "error": str(exc), "authority": "go-tool-runtime"})
            yield Event(EventType.TURN_END, {"runtime": "harness", "stop_reason": "bootstrap_error"})
            return

        saw_error = False
        stop_reason = ""
        scoped_source = self._scoped_source(source)
        async for event in super().run(prompt, source=scoped_source, display=display):
            if event.type is EventType.ERROR:
                saw_error = True
                self._last_result = "failed"
                self._last_summary = str(event.data.get("error") or "Harness runtime error")
            elif event.type is EventType.TURN_END:
                stop_reason = str(event.data.get("stop_reason") or "")
            yield event
        if not saw_error:
            self._last_result = "success"
            self._last_summary = f"Harness turn completed: {stop_reason or 'end_turn'}"

    async def health(self) -> dict[str, Any]:
        base = await super().health()
        capabilities = dict(base.get("capabilities") or {})
        capabilities["tool_runtime_bootstrap"] = True
        capabilities["tool_runtime_repeat_query"] = True
        capabilities["permission_bridge"] = self._permission_bridge_enabled
        base["capabilities"] = capabilities
        base["information_authority"] = "go-tool-runtime"
        base["execution_authority"] = "AI-Engineering-OS"
        base["bootstrap_session_created"] = self._bootstrap is not None
        base["engineering_project_id"] = self._bootstrap_project or None
        base["engineering_job_id"] = self._engineering_job_id or None
        return base

    async def aclose(self) -> None:
        try:
            if self._bootstrap is not None:
                try:
                    await asyncio.to_thread(
                        self._bootstrap_client.finish,
                        self._bootstrap.session_id,
                        summary=self._last_summary,
                        result=self._last_result,
                    )
                except ToolRuntimeBootstrapError:
                    pass
        finally:
            await super().aclose()
            if self._owns_bootstrap_client:
                self._bootstrap_client.close()


__all__ = ["EngineeringHarnessRuntime"]
