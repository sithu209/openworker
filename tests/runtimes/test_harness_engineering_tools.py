from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from coworker.engine import ApprovalOutcome
from coworker.permissions import PermissionEngine
from coworker.runtimes.harness_engineering_tools import (
    EngineeringOSInvocationScope,
    EngineeringOSToolClient,
    EngineeringOSToolDiscoveryError,
    EngineeringOSToolInvocationError,
    HarnessEngineeringToolGateway,
)
from coworker.runtimes.harness_permissions import (
    HarnessPermissionBridge,
    HarnessToolContextRegistry,
)


def _mcp_payload() -> dict:
    return {
        "tools": [
            {
                "name": "workspace__inspect",
                "description": "read workspace",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "annotations": {
                    "canonical_tool_id": "workspace.inspect",
                    "side_effect": "read",
                    "requires_job_scope": False,
                    "cost_class": "low",
                },
            },
            {
                "name": "bridge__export_site_gltf",
                "description": "export bridge",
                "inputSchema": {
                    "type": "object",
                    "properties": {"site_fit_artifact_id": {"type": "string"}},
                    "required": ["site_fit_artifact_id"],
                    "additionalProperties": False,
                },
                "annotations": {
                    "canonical_tool_id": "bridge.export_site_gltf",
                    "side_effect": "compute",
                    "requires_job_scope": True,
                    "cost_class": "medium",
                },
            },
            {
                "name": "budget__calculate",
                "description": "mutating budget flow",
                "inputSchema": {
                    "type": "object",
                    "properties": {"pcces_project_id": {"type": "integer"}},
                    "required": ["pcces_project_id"],
                    "additionalProperties": False,
                },
                "annotations": {
                    "canonical_tool_id": "budget.calculate",
                    "side_effect": "mutate",
                    "requires_job_scope": True,
                    "cost_class": "high",
                },
            },
        ]
    }


def _transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/api/v1/ai/tools/mcp":
            return httpx.Response(200, json=_mcp_payload())
        if request.method == "POST" and request.url.path == "/api/v1/ai/tools/bridge.export_site_gltf/invoke":
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "tool": "bridge.export_site_gltf",
                    "run_id": "run-1",
                    "summary": "generated",
                    "result": {"body": body},
                    "artifacts": [{"id": "artifact-1"}],
                    "trace": ["gateway"],
                    "warnings": [],
                    "assumptions": [],
                    "evidence": [],
                    "next_possible_tools": ["scene.assemble_godot"],
                    "retryable": False,
                    "recovery_actions": [],
                    "error": None,
                },
            )
        return httpx.Response(404, json={"error": "not_found"})

    return httpx.MockTransport(handler)


def _gateway(seen: list[httpx.Request]):
    raw_client = httpx.Client(transport=_transport(seen))
    client = EngineeringOSToolClient("http://engineering-os", client=raw_client)
    contexts = HarnessToolContextRegistry()
    gateway = HarnessEngineeringToolGateway(client, contexts)
    return raw_client, client, contexts, gateway


def test_dynamic_discovery_preserves_os_canonical_authority() -> None:
    seen: list[httpx.Request] = []
    raw, client, contexts, gateway = _gateway(seen)
    try:
        tools = gateway.refresh()
        assert [tool.exposed_name for tool in tools] == [
            "workspace__inspect",
            "bridge__export_site_gltf",
            "budget__calculate",
        ]
        assert tools[1].canonical_tool_id == "bridge.export_site_gltf"
        assert tools[1].metadata.requires_job_scope is True
        assert tools[1].metadata.requires_approval is False
        assert tools[2].metadata.requires_approval is True
        schemas = gateway.model_schemas()
        assert schemas[1]["function"]["name"] == "bridge__export_site_gltf"
        assert schemas[1]["function"]["parameters"]["required"] == ["site_fit_artifact_id"]
        assert len(contexts) == 0
    finally:
        raw.close()


def test_discovery_rejects_tool_without_canonical_annotation() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"tools": [{"name": "bad", "inputSchema": {}, "annotations": {}}]},
        )

    raw = httpx.Client(transport=httpx.MockTransport(handler))
    client = EngineeringOSToolClient("http://engineering-os", client=raw)
    try:
        with pytest.raises(EngineeringOSToolDiscoveryError, match="canonical_tool_id"):
            client.discover()
    finally:
        raw.close()


def test_prepare_call_is_h4_authoritative_context_producer() -> None:
    seen: list[httpx.Request] = []
    raw, _client, contexts, gateway = _gateway(seen)
    try:
        gateway.refresh()
        context = gateway.prepare_call(
            "call-42",
            "bridge__export_site_gltf",
            {"site_fit_artifact_id": "sf-1"},
        )
        assert contexts.resolve("call-42") == context
        assert context.metadata.canonical_tool_id == "bridge.export_site_gltf"
        assert context.arguments == {"site_fit_artifact_id": "sf-1"}
        gateway.finish_call("call-42")
        assert contexts.resolve("call-42") is None
    finally:
        raw.close()


@pytest.mark.asyncio
async def test_mutating_os_tool_routes_through_openworker_permission_bridge(tmp_path: Path) -> None:
    seen_http: list[httpx.Request] = []
    raw, _client, contexts, gateway = _gateway(seen_http)
    approvals = []

    async def approver(request):
        approvals.append(request)
        return ApprovalOutcome.ONCE

    try:
        gateway.refresh()
        gateway.prepare_call("call-budget", "budget__calculate", {"pcces_project_id": 7})
        bridge = HarnessPermissionBridge(
            permissions=PermissionEngine(tmp_path),
            approver=approver,
            resolve_context=contexts.resolve,
        )
        result = await bridge(
            {"sessionId": "s-1", "toolCall": {"toolCallId": "call-budget"}}
        )
        assert result == {
            "outcome": {"outcome": "selected", "optionId": "allow-once"}
        }
        assert len(approvals) == 1
        assert approvals[0].tool_name == "budget__calculate"
        assert approvals[0].metadata.canonical_tool_id == "budget.calculate"
    finally:
        raw.close()


def test_prepared_call_invokes_canonical_os_endpoint_and_always_cleans_context() -> None:
    seen: list[httpx.Request] = []
    raw, _client, contexts, gateway = _gateway(seen)
    try:
        gateway.refresh()
        gateway.prepare_call(
            "call-9",
            "bridge__export_site_gltf",
            {"site_fit_artifact_id": "sf-9"},
        )
        result = gateway.invoke_prepared(
            "call-9",
            EngineeringOSInvocationScope(
                project_id="project-1",
                job_id="job-9",
                component_id="bridge-a",
            ),
        )
        assert result["status"] == "ok"
        assert result["artifacts"][0]["id"] == "artifact-1"
        assert contexts.resolve("call-9") is None
        request = [r for r in seen if r.method == "POST"][-1]
        assert request.url.path == "/api/v1/ai/tools/bridge.export_site_gltf/invoke"
        body = json.loads(request.content)
        assert body == {
            "project_id": "project-1",
            "job_id": "job-9",
            "arguments": {"site_fit_artifact_id": "sf-9"},
            "component_id": "bridge-a",
        }
    finally:
        raw.close()


def test_job_scoped_tool_fails_closed_without_project_and_job() -> None:
    seen: list[httpx.Request] = []
    raw, _client, contexts, gateway = _gateway(seen)
    try:
        gateway.refresh()
        gateway.prepare_call(
            "call-no-scope",
            "bridge__export_site_gltf",
            {"site_fit_artifact_id": "sf"},
        )
        with pytest.raises(EngineeringOSToolInvocationError, match="requires project_id and job_id"):
            gateway.invoke_prepared(
                "call-no-scope",
                EngineeringOSInvocationScope(project_id="", job_id=""),
            )
        assert contexts.resolve("call-no-scope") is None
    finally:
        raw.close()
