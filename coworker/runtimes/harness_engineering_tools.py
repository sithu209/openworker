"""H6 dynamic Engineering-OS tool gateway for the DeepSeek Harness runtime.

AI-Engineering-OS remains the canonical authority for engineering tool names,
schemas and execution. OpenWorker discovers the OS MCP-compatible export at
runtime, exposes the returned model schemas, and maps each Harness tool-call id
to canonical context before permission handling.

This module deliberately does not copy OS recipes or tool definitions into
OpenWorker. Unknown/ambiguous discovery data and unprepared invocations fail
closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.parse import quote

import httpx

from .harness_permissions import HarnessToolContext, HarnessToolContextRegistry


class EngineeringOSToolError(RuntimeError):
    """Base error for dynamic Engineering-OS tool discovery/invocation."""


class EngineeringOSToolDiscoveryError(EngineeringOSToolError):
    """Raised when the OS tool export cannot be trusted."""


class EngineeringOSToolInvocationError(EngineeringOSToolError):
    """Raised when the OS rejects or cannot complete an invocation."""


@dataclass(frozen=True)
class EngineeringOSToolMetadata:
    """Permission-facing metadata derived from canonical OS annotations."""

    category: str
    canonical_tool_id: str
    side_effect: str
    requires_job_scope: bool
    cost_class: str = ""
    requires_approval: bool = False


@dataclass(frozen=True)
class EngineeringOSTool:
    """One dynamically discovered, invokable Engineering-OS tool."""

    exposed_name: str
    canonical_tool_id: str
    description: str
    input_schema: dict[str, Any]
    metadata: EngineeringOSToolMetadata

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.exposed_name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass(frozen=True)
class EngineeringOSInvocationScope:
    project_id: str
    job_id: str
    component_id: str = ""
    allow_publish: bool = False


class EngineeringOSToolClient:
    """Thin HTTP client over AI-Engineering-OS's native agent API."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout_s: float = 1800.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            raise ValueError("Engineering-OS base_url is required")
        self.base_url = base
        self.token = str(token or "").strip()
        self._owns_client = client is None
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client = client or httpx.Client(timeout=timeout_s, headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "EngineeringOSToolClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def discover(self) -> list[EngineeringOSTool]:
        try:
            response = self.client.get(f"{self.base_url}/api/v1/ai/tools/mcp")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineeringOSToolDiscoveryError(
                f"Engineering-OS tool discovery failed: {exc}"
            ) from exc

        raw_tools = payload.get("tools") if isinstance(payload, dict) else None
        if not isinstance(raw_tools, list):
            raise EngineeringOSToolDiscoveryError("Engineering-OS MCP export has no tools array")

        tools: list[EngineeringOSTool] = []
        exposed_seen: set[str] = set()
        canonical_seen: set[str] = set()
        for raw in raw_tools:
            if not isinstance(raw, dict):
                raise EngineeringOSToolDiscoveryError("Engineering-OS MCP tool must be an object")
            name = raw.get("name")
            annotations = raw.get("annotations")
            input_schema = raw.get("inputSchema")
            if not isinstance(name, str) or not name.strip():
                raise EngineeringOSToolDiscoveryError("Engineering-OS MCP tool has no name")
            if not isinstance(annotations, dict):
                raise EngineeringOSToolDiscoveryError(f"{name}: missing annotations")
            canonical = annotations.get("canonical_tool_id")
            if not isinstance(canonical, str) or not canonical.strip():
                raise EngineeringOSToolDiscoveryError(f"{name}: missing canonical_tool_id")
            if not isinstance(input_schema, dict):
                raise EngineeringOSToolDiscoveryError(f"{name}: inputSchema must be an object")
            if name in exposed_seen:
                raise EngineeringOSToolDiscoveryError(f"duplicate exposed tool name: {name}")
            if canonical in canonical_seen:
                raise EngineeringOSToolDiscoveryError(f"duplicate canonical tool id: {canonical}")
            exposed_seen.add(name)
            canonical_seen.add(canonical)

            side_effect = str(annotations.get("side_effect") or "").strip().lower()
            # OS read/compute tools are non-consequential. Any unknown or mutating side-effect
            # class asks OpenWorker for approval rather than silently broadening authority.
            requires_approval = side_effect not in {"read", "compute"}
            metadata = EngineeringOSToolMetadata(
                category="engineering_os",
                canonical_tool_id=canonical,
                side_effect=side_effect,
                requires_job_scope=bool(annotations.get("requires_job_scope")),
                cost_class=str(annotations.get("cost_class") or ""),
                requires_approval=requires_approval,
            )
            tools.append(
                EngineeringOSTool(
                    exposed_name=name,
                    canonical_tool_id=canonical,
                    description=str(raw.get("description") or ""),
                    input_schema=input_schema,
                    metadata=metadata,
                )
            )
        return tools

    def invoke(
        self,
        tool: EngineeringOSTool,
        arguments: dict[str, Any],
        scope: EngineeringOSInvocationScope,
    ) -> dict[str, Any]:
        if tool.metadata.requires_job_scope and (not scope.project_id or not scope.job_id):
            raise EngineeringOSToolInvocationError(
                f"{tool.canonical_tool_id} requires project_id and job_id"
            )
        body = {
            "project_id": scope.project_id,
            "job_id": scope.job_id,
            "arguments": arguments or {},
        }
        if scope.component_id:
            body["component_id"] = scope.component_id
        if scope.allow_publish:
            body["allow_publish"] = True
        encoded_id = quote(tool.canonical_tool_id, safe="._-")
        try:
            response = self.client.post(
                f"{self.base_url}/api/v1/ai/tools/{encoded_id}/invoke",
                json=body,
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineeringOSToolInvocationError(
                f"{tool.canonical_tool_id} invocation transport failed: {exc}"
            ) from exc
        if response.is_error:
            raise EngineeringOSToolInvocationError(
                f"{tool.canonical_tool_id} invocation failed ({response.status_code}): {payload}"
            )
        if not isinstance(payload, dict):
            raise EngineeringOSToolInvocationError(
                f"{tool.canonical_tool_id} returned a non-object result"
            )
        return payload


class HarnessEngineeringToolGateway:
    """Dynamic tool catalog plus authoritative H4 call-context producer.

    The required ordering for a Harness call is:
      prepare_call -> ACP permission decision -> invoke_prepared -> finish_call

    `invoke_prepared(..., finish=True)` performs cleanup in a finally block. A caller
    that needs to inspect the context longer may pass finish=False and call finish_call.
    """

    def __init__(
        self,
        client: EngineeringOSToolClient,
        contexts: HarnessToolContextRegistry,
    ) -> None:
        self.client = client
        self.contexts = contexts
        self._tools: dict[str, EngineeringOSTool] = {}

    def refresh(self) -> list[EngineeringOSTool]:
        tools = self.client.discover()
        self._tools = {tool.exposed_name: tool for tool in tools}
        return list(tools)

    def tools(self) -> list[EngineeringOSTool]:
        return list(self._tools.values())

    def model_schemas(self) -> list[dict[str, Any]]:
        return [tool.openai_schema() for tool in self._tools.values()]

    def resolve_tool(self, exposed_name: str) -> EngineeringOSTool:
        tool = self._tools.get(exposed_name)
        if tool is None:
            raise EngineeringOSToolDiscoveryError(
                f"Harness requested undiscovered Engineering-OS tool: {exposed_name}"
            )
        return tool

    def prepare_call(
        self,
        call_id: str,
        exposed_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> HarnessToolContext:
        tool = self.resolve_tool(exposed_name)
        context = HarnessToolContext(
            tool_call_id=call_id,
            tool_name=exposed_name,
            arguments=dict(arguments or {}),
            metadata=tool.metadata,
        )
        self.contexts.register(context)
        return context

    def invoke_prepared(
        self,
        call_id: str,
        scope: EngineeringOSInvocationScope,
        *,
        finish: bool = True,
    ) -> dict[str, Any]:
        context = self.contexts.resolve(call_id)
        if context is None:
            raise EngineeringOSToolInvocationError(
                f"Harness call {call_id!r} has no prepared canonical context"
            )
        tool = self.resolve_tool(context.tool_name)
        try:
            return self.client.invoke(tool, context.arguments, scope)
        finally:
            if finish:
                self.finish_call(call_id)

    def finish_call(self, call_id: str) -> None:
        self.contexts.discard(call_id)


__all__ = [
    "EngineeringOSInvocationScope",
    "EngineeringOSTool",
    "EngineeringOSToolClient",
    "EngineeringOSToolDiscoveryError",
    "EngineeringOSToolError",
    "EngineeringOSToolInvocationError",
    "EngineeringOSToolMetadata",
    "HarnessEngineeringToolGateway",
]
