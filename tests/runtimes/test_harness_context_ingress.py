from __future__ import annotations

import json

import httpx

from coworker.runtimes.harness_context_ingress import HarnessContextIngressServer
from coworker.runtimes.harness_engineering_tools import (
    EngineeringOSToolClient,
    HarnessEngineeringToolGateway,
)
from coworker.runtimes.harness_permissions import HarnessToolContextRegistry


def _os_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/ai/tools/mcp":
            return httpx.Response(
                200,
                json={
                    "tools": [
                        {
                            "name": "budget__calculate",
                            "description": "budget",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"amount": {"type": "number"}},
                                "required": ["amount"],
                                "additionalProperties": False,
                            },
                            "annotations": {
                                "canonical_tool_id": "budget.calculate",
                                "side_effect": "mutate",
                                "requires_job_scope": True,
                                "cost_class": "high",
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "not_found"})

    return httpx.MockTransport(handler)


def _fixture():
    raw = httpx.Client(transport=_os_transport())
    os_client = EngineeringOSToolClient("http://engineering-os", client=raw)
    contexts = HarnessToolContextRegistry()
    gateway = HarnessEngineeringToolGateway(os_client, contexts)
    gateway.refresh()
    server = HarnessContextIngressServer(gateway, token="test-secret")
    return raw, contexts, server


def test_ingress_registers_only_openworker_resolved_canonical_context() -> None:
    raw, contexts, server = _fixture()
    try:
        with server:
            address = server.address
            response = httpx.post(
                f"{address.base_url}/v1/harness/tool-context",
                headers={"Authorization": "Bearer test-secret"},
                json={
                    "callId": "call-1",
                    "name": "budget__calculate",
                    "arguments": {"amount": 9},
                },
            )
            assert response.status_code == 201
            assert response.json()["canonicalToolId"] == "budget.calculate"
            context = contexts.resolve("call-1")
            assert context is not None
            assert context.metadata.canonical_tool_id == "budget.calculate"
            assert context.metadata.requires_approval is True
    finally:
        server.close()
        raw.close()


def test_ingress_rejects_missing_auth_and_policy_field_smuggling() -> None:
    raw, contexts, server = _fixture()
    try:
        with server:
            url = f"{server.address.base_url}/v1/harness/tool-context"
            no_auth = httpx.post(
                url,
                json={"callId": "call-1", "name": "budget__calculate", "arguments": {}},
            )
            assert no_auth.status_code == 401

            smuggle = httpx.post(
                url,
                headers={"Authorization": "Bearer test-secret"},
                json={
                    "callId": "call-1",
                    "name": "budget__calculate",
                    "arguments": {},
                    "side_effect": "read",
                },
            )
            assert smuggle.status_code == 400
            assert contexts.resolve("call-1") is None
    finally:
        server.close()
        raw.close()


def test_ingress_rejects_unknown_tool_and_duplicate_live_call_id() -> None:
    raw, contexts, server = _fixture()
    try:
        with server:
            url = f"{server.address.base_url}/v1/harness/tool-context"
            headers = {"Authorization": "Bearer test-secret"}
            unknown = httpx.post(
                url,
                headers=headers,
                json={"callId": "call-x", "name": "fake__tool", "arguments": {}},
            )
            assert unknown.status_code == 409

            first = httpx.post(
                url,
                headers=headers,
                json={"callId": "call-2", "name": "budget__calculate", "arguments": {"amount": 1}},
            )
            assert first.status_code == 201
            duplicate = httpx.post(
                url,
                headers=headers,
                json={"callId": "call-2", "name": "budget__calculate", "arguments": {"amount": 2}},
            )
            assert duplicate.status_code == 409
            assert contexts.resolve("call-2").arguments == {"amount": 1}
    finally:
        server.close()
        raw.close()


def test_ingress_delete_discards_context() -> None:
    raw, contexts, server = _fixture()
    try:
        with server:
            url = f"{server.address.base_url}/v1/harness/tool-context"
            headers = {"Authorization": "Bearer test-secret"}
            assert httpx.post(
                url,
                headers=headers,
                json={"callId": "call-3", "name": "budget__calculate", "arguments": {"amount": 3}},
            ).status_code == 201
            assert contexts.resolve("call-3") is not None
            response = httpx.request(
                "DELETE",
                url,
                headers={**headers, "Content-Type": "application/json"},
                content=json.dumps({"callId": "call-3"}),
            )
            assert response.status_code == 200
            assert contexts.resolve("call-3") is None
    finally:
        server.close()
        raw.close()
