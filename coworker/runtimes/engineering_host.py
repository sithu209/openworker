"""One-command composition root for the OpenWorker engineering Harness.

Authority order is deliberate:

1. go-tool-runtime -> information/context bootstrap before execution starts;
2. OpenWorker -> fixed host/workspace Job binding + permission/lifecycle policy;
3. AI-Engineering-OS -> Project/Job identity + canonical engineering tools;
4. DeepSeek Harness -> model/ACP host.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from ..engine import ApprovalOutcome, Approver, PermissionRequest
from ..events import Event
from ..permissions import Mode, PermissionEngine
from .engineering_harness import EngineeringHarnessRuntime
from .engineering_scope import EngineeringOSScopeClient, EngineeringScope
from .harness import HarnessProcessConfig, HarnessRuntimeError
from .harness_context_ingress import HarnessContextIngressServer
from .harness_engineering_tools import EngineeringOSToolClient, HarnessEngineeringToolGateway
from .harness_permissions import HarnessPermissionBridge, HarnessToolContextRegistry
from .job_binding import JobBindingError, JobBindingStore
from .tool_runtime_bootstrap import ToolRuntimeBootstrapClient


async def _deny(_request: PermissionRequest) -> ApprovalOutcome:
    return ApprovalOutcome.DENY


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


class EngineeringHarnessHost:
    """Compose and own one engineering Harness session for a bound Project Workspace."""

    def __init__(
        self,
        *,
        workspace: str | os.PathLike[str] | None = None,
        process_config: HarnessProcessConfig | None = None,
        engineering_os_base_url: str | None = None,
        engineering_os_token: str | None = None,
        tool_runtime_base_url: str | None = None,
        mode: Mode = Mode.INTERACTIVE,
        approver: Approver | None = None,
        allow_publish: bool | None = None,
        component_id: str = "",
        scope_client: EngineeringOSScopeClient | None = None,
        tool_client: EngineeringOSToolClient | None = None,
        bootstrap_client: ToolRuntimeBootstrapClient | None = None,
    ) -> None:
        self.workspace = Path(workspace or os.getcwd()).expanduser().resolve()
        if not self.workspace.is_dir():
            raise HarnessRuntimeError(f"Project Workspace does not exist: {self.workspace}")
        self.engineering_os_base_url = str(
            engineering_os_base_url
            or os.environ.get("OPENWORKER_ENGINEERING_OS_BASE_URL")
            or "http://127.0.0.1:8080"
        ).strip().rstrip("/")
        self.engineering_os_token = str(
            engineering_os_token
            if engineering_os_token is not None
            else os.environ.get("OPENWORKER_ENGINEERING_OS_TOKEN", "")
        ).strip()
        self.tool_runtime_base_url = str(
            tool_runtime_base_url
            or os.environ.get("OPENWORKER_TOOL_RUNTIME_URL")
            or "http://127.0.0.1:8848"
        ).strip().rstrip("/")
        self.mode = mode
        self.approver = approver or _deny
        self.allow_publish = (
            _truthy(os.environ.get("OPENWORKER_ENGINEERING_ALLOW_PUBLISH"))
            if allow_publish is None
            else bool(allow_publish)
        )
        self.component_id = str(component_id or "").strip()
        self._provided_process_config = process_config
        self._scope_client = scope_client or EngineeringOSScopeClient(
            self.engineering_os_base_url,
            token=self.engineering_os_token,
        )
        self._owns_scope_client = scope_client is None
        self._tool_client = tool_client or EngineeringOSToolClient(
            self.engineering_os_base_url,
            token=self.engineering_os_token,
        )
        self._owns_tool_client = tool_client is None
        self._bootstrap_client = bootstrap_client or ToolRuntimeBootstrapClient(
            self.tool_runtime_base_url
        )
        self._owns_bootstrap_client = bootstrap_client is None
        self._binding_store = JobBindingStore(self.workspace)
        self._scope: EngineeringScope | None = None
        self._contexts: HarnessToolContextRegistry | None = None
        self._gateway: HarnessEngineeringToolGateway | None = None
        self._ingress: HarnessContextIngressServer | None = None
        self._runtime: EngineeringHarnessRuntime | None = None
        self._temp_config: tempfile.TemporaryDirectory[str] | None = None
        self._prepare_lock = asyncio.Lock()
        self._closed = False

    @property
    def scope(self) -> EngineeringScope | None:
        return self._scope

    @property
    def runtime(self) -> EngineeringHarnessRuntime | None:
        return self._runtime

    async def prepare(self, initial_request: str) -> None:
        if self._runtime is not None:
            return
        async with self._prepare_lock:
            if self._runtime is not None:
                return
            if self._closed:
                raise HarnessRuntimeError("engineering host is closed")
            request = str(initial_request or "").strip()
            if not request:
                raise HarnessRuntimeError("initial request must not be empty")
            try:
                # Information authority must be consulted before any OS execution
                # scope is created or resumed. The model starts by reading the
                # tool knowledge, not by guessing which executor to invoke.
                preflight = await asyncio.to_thread(
                    self._bootstrap_client.start,
                    self.workspace,
                    request,
                    task="Determine the correct tools, execution constraints, host requirements, and success criteria before starting work.",
                    project=self.workspace.name or "workspace",
                    agent="openworker-harness",
                )

                # A job is pinned to the machine and workspace chosen at creation.
                # Later Action invocations on another machine fail closed instead
                # of silently continuing the same local job elsewhere.
                binding = self._binding_store.load()
                if binding is not None:
                    scope = binding.scope()
                else:
                    scope = await asyncio.to_thread(
                        self._scope_client.ensure,
                        self.workspace,
                        request,
                    )
                    self._binding_store.create(scope)

                contexts = HarnessToolContextRegistry()
                gateway = HarnessEngineeringToolGateway(self._tool_client, contexts)
                await asyncio.to_thread(gateway.refresh)
                ingress = HarnessContextIngressServer(gateway)
                address = ingress.start()
                permissions = PermissionEngine(self.workspace, mode=self.mode)
                permission_bridge = HarnessPermissionBridge(
                    permissions=permissions,
                    approver=self.approver,
                    resolve_context=contexts.resolve,
                )
                process = self._provided_process_config or self._official_process_config()
                env = dict(process.env)
                env.update(
                    {
                        "OPENWORKER_ENGINEERING_OS_BASE_URL": self.engineering_os_base_url,
                        "OPENWORKER_HARNESS_CONTEXT_URL": address.base_url,
                        "OPENWORKER_HARNESS_CONTEXT_TOKEN": address.token,
                        "OPENWORKER_ENGINEERING_PROJECT_ID": scope.project_id,
                        "OPENWORKER_ENGINEERING_JOB_ID": scope.job_id,
                        "OPENWORKER_ASSIGNED_HOST": self._binding_store.current_host(),
                        "OPENWORKER_JOB_WORKSPACE": str(self.workspace),
                    }
                )
                if self.engineering_os_token:
                    env["OPENWORKER_ENGINEERING_OS_TOKEN"] = self.engineering_os_token
                if self.component_id:
                    env["OPENWORKER_ENGINEERING_COMPONENT_ID"] = self.component_id
                if self.allow_publish:
                    env["OPENWORKER_ENGINEERING_ALLOW_PUBLISH"] = "1"
                else:
                    env.pop("OPENWORKER_ENGINEERING_ALLOW_PUBLISH", None)
                process = replace(process, env=env)
                runtime = EngineeringHarnessRuntime(
                    process_config=process,
                    workspace=self.workspace,
                    bootstrap_client=self._bootstrap_client,
                    bootstrap_project=scope.project_id,
                    initial_bootstrap=preflight,
                    permission_handler=permission_bridge,
                )
            except (JobBindingError, BaseException):
                ingress_obj = locals().get("ingress")
                if isinstance(ingress_obj, HarnessContextIngressServer):
                    ingress_obj.close()
                raise
            self._scope = scope
            self._contexts = contexts
            self._gateway = gateway
            self._ingress = ingress
            self._runtime = runtime

    async def run(
        self,
        user_input: str,
        *,
        source: Optional[dict[str, Any]] = None,
        display: Optional[str] = None,
    ) -> AsyncIterator[Event]:
        await self.prepare(user_input)
        assert self._runtime is not None
        async for event in self._runtime.run(user_input, source=source, display=display):
            yield event

    async def health(self) -> dict[str, Any]:
        runtime = self._runtime
        if runtime is None:
            return {
                "runtime": "engineering-harness",
                "prepared": False,
                "information_authority": "go-tool-runtime",
                "execution_authority": "AI-Engineering-OS",
            }
        data = await runtime.health()
        data["prepared"] = True
        if self._scope is not None:
            data["project_id"] = self._scope.project_id
            data["job_id"] = self._scope.job_id
        binding = self._binding_store.load()
        if binding is not None:
            data["assigned_host"] = binding.assigned_host
            data["workspace_root"] = binding.workspace_root
        data["publish_capability_enabled"] = self.allow_publish
        return data

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._runtime is not None:
                await self._runtime.aclose()
        finally:
            if self._ingress is not None:
                await asyncio.to_thread(self._ingress.close)
            if self._contexts is not None:
                self._contexts.clear()
            if self._owns_tool_client:
                self._tool_client.close()
            if self._owns_scope_client:
                self._scope_client.close()
            if self._owns_bootstrap_client:
                self._bootstrap_client.close()
            if self._temp_config is not None:
                self._temp_config.cleanup()

    def _official_process_config(self) -> HarnessProcessConfig:
        root_raw = os.environ.get("DSH_HARNESS_ROOT", "").strip()
        node_raw = os.environ.get("OPENWORKER_HARNESS_NODE", "").strip()
        if not root_raw or not node_raw:
            raise HarnessRuntimeError(
                "one-command official Harness requires explicit DSH_HARNESS_ROOT and OPENWORKER_HARNESS_NODE"
            )
        root = Path(root_raw).expanduser().resolve()
        node = Path(node_raw).expanduser().resolve()
        plugin = (Path(__file__).resolve().parents[2] / "harness" / "upstream-plugin" / "openworker-engineering-tools.ts").resolve()
        official_config = root / "examples" / "acp-agent" / "cordis.yml"
        bin_ts = root / "packages" / "examples" / "acp-demo" / "src" / "bin.ts"
        tsconfig = root / "tsconfig.json"
        for required in (root, node, plugin, official_config, bin_ts, tsconfig):
            if not required.exists():
                raise HarnessRuntimeError(f"required Harness bootstrap path does not exist: {required}")
        if not node.is_file():
            raise HarnessRuntimeError(f"OPENWORKER_HARNESS_NODE is not a file: {node}")
        temp = tempfile.TemporaryDirectory(prefix="openworker-engineering-harness-")
        self._temp_config = temp
        config = Path(temp.name) / "cordis.openworker.yml"
        base = official_config.read_text(encoding="utf-8")
        plugin_row = (
            "\n\n# OpenWorker engineering authority plugin.\n"
            "- id: openworker-engineering-tools\n"
            f"  name: {_yaml_string(plugin.as_uri())}\n"
        )
        config.write_text(base + plugin_row, encoding="utf-8")
        env = {
            "TSX_TSCONFIG_PATH": str(tsconfig),
            "DSH_PERMISSION_MODE": os.environ.get("DSH_PERMISSION_MODE", "workspace-write"),
        }
        return HarnessProcessConfig(
            command=(
                str(node),
                "--import",
                "tsx",
                str(bin_ts),
                "--config",
                str(config),
            ),
            cwd=root,
            env=env,
            startup_timeout_s=30.0,
            request_timeout_s=300.0,
        )


__all__ = ["EngineeringHarnessHost"]
