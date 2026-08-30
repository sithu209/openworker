from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from coworker.events import EventType
from coworker.runtimes.engineering_host import EngineeringHarnessHost
from coworker.runtimes.engineering_scope import EngineeringOSScopeClient
from coworker.runtimes.harness import HarnessProcessConfig
from coworker.runtimes.harness_engineering_tools import EngineeringOSToolClient
from coworker.runtimes.tool_runtime_bootstrap import ToolRuntimeBootstrapClient

FIXTURE = Path(__file__).parent / "fixtures" / "mock_acp_server.py"


def _process(tmp_path: Path) -> HarnessProcessConfig:
    return HarnessProcessConfig(
        command=(sys.executable, str(FIXTURE)),
        cwd=tmp_path,
        startup_timeout_s=5.0,
        request_timeout_s=5.0,
    )


def _os_transport(seen: list[tuple[str, str, dict | None]]) -> httpx.MockTransport:
    projects: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/api/v1/projects":
            return httpx.Response(200, json={"items": projects})
        if request.method == "POST" and request.url.path == "/api/v1/projects":
            created = {"id":"prj-host","status":"draft",**body}
            projects.append(created)
            return httpx.Response(201, json=created)
        if request.method == "POST" and request.url.path == "/api/v1/jobs":
            return httpx.Response(201, json={"id":"job-host","status":"draft",**body})
        if request.method == "GET" and request.url.path == "/api/v1/ai/tools/mcp":
            return httpx.Response(
                200,
                json={
                    "tools":[
                        {
                            "name":"workspace__inspect",
                            "description":"inspect",
                            "inputSchema":{"type":"object","properties":{},"additionalProperties":False},
                            "annotations":{
                                "canonical_tool_id":"workspace.inspect",
                                "side_effect":"read",
                                "requires_job_scope":False,
                                "cost_class":"low",
                            },
                        },
                        {
                            "name":"workspace__publish_artifact",
                            "description":"publish",
                            "inputSchema":{
                                "type":"object",
                                "properties":{"artifact_id":{"type":"string"},"workspace_root":{"type":"string"}},
                                "required":["artifact_id","workspace_root"],
                            },
                            "annotations":{
                                "canonical_tool_id":"workspace.publish_artifact",
                                "side_effect":"publish",
                                "requires_job_scope":True,
                                "cost_class":"low",
                            },
                        },
                    ]
                },
            )
        return httpx.Response(404, json={"error":"not_found"})

    return httpx.MockTransport(handler)


def _runtime_transport(root: Path, seen: list[tuple[str,dict]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        seen.append((request.url.path, body))
        if request.url.path == "/agent/start":
            return httpx.Response(
                200,
                json={
                    "session_id":"rt-session",
                    "project":body["project"],
                    "goal":body["goal"],
                    "information_pack":{
                        "source":"agent_information_pack",
                        "workspace":{"workspace_id":"ws","workspace_root":str(root.resolve())},
                    },
                    "prompt":(
                        "<AgentInformationPack>\n"
                        f"workspace_root={root.resolve()}\n"
                        "information_authority=go-tool-runtime\n"
                        "execution_authority=AI-Engineering-OS\n"
                        "</AgentInformationPack>"
                    ),
                },
            )
        if request.url.path == "/agent/finish":
            return httpx.Response(200, json={"session_id":body["session_id"],"status":"success"})
        return httpx.Response(404, json={"error":"not_found"})
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_host_composes_scope_bootstrap_tools_ingress_and_harness(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("bootstrap\n", encoding="utf-8")
    os_seen: list[tuple[str,str,dict|None]] = []
    rt_seen: list[tuple[str,dict]] = []
    os_http = httpx.Client(transport=_os_transport(os_seen))
    rt_http = httpx.Client(transport=_runtime_transport(tmp_path,rt_seen))
    scope_client = EngineeringOSScopeClient("http://engineering-os",client=os_http)
    tool_client = EngineeringOSToolClient("http://engineering-os",client=os_http)
    bootstrap_client = ToolRuntimeBootstrapClient("http://tool-runtime",client=rt_http)
    host = EngineeringHarnessHost(
        workspace=tmp_path,
        process_config=_process(tmp_path),
        engineering_os_base_url="http://engineering-os",
        scope_client=scope_client,
        tool_client=tool_client,
        bootstrap_client=bootstrap_client,
        allow_publish=True,
    )
    try:
        events = [event async for event in host.run("build deliverables")]
        health = await host.health()
        assert host.scope is not None
        assert host.scope.project_id == "prj-host"
        assert host.scope.job_id == "job-host"
        assert host.runtime is not None
        env = host.runtime.process_config.env
        assert env["OPENWORKER_ENGINEERING_PROJECT_ID"] == "prj-host"
        assert env["OPENWORKER_ENGINEERING_JOB_ID"] == "job-host"
        assert env["OPENWORKER_ENGINEERING_ALLOW_PUBLISH"] == "1"
        assert env["OPENWORKER_HARNESS_CONTEXT_URL"].startswith("http://127.0.0.1:")
        assert env["OPENWORKER_HARNESS_CONTEXT_TOKEN"]
        assert health["prepared"] is True
        assert health["project_id"] == "prj-host"
        assert health["job_id"] == "job-host"
        message = next(event for event in events if event.type is EventType.ASSISTANT_MESSAGE)
        assert "information_authority=go-tool-runtime" in message.data["content"]
        assert "build deliverables" in message.data["content"]
        start = next(body for path,body in rt_seen if path == "/agent/start")
        # go-tool is consulted before AI-Engineering-OS creates its project, so
        # the information session uses the stable workspace identity rather than
        # an OS project id that does not exist yet.
        assert start["project"] == tmp_path.name
        assert start["project"] != "prj-host"
        assert start["workspace_root"] == str(tmp_path.resolve())
    finally:
        await host.aclose()
        os_http.close(); rt_http.close()
    assert any(path == "/agent/finish" for path,_ in rt_seen)
    assert [pair[:2] for pair in os_seen].count(("GET","/api/v1/ai/tools/mcp")) == 1


@pytest.mark.asyncio
async def test_host_does_not_enable_publish_capability_by_default(tmp_path: Path) -> None:
    os_http = httpx.Client(transport=_os_transport([]))
    rt_http = httpx.Client(transport=_runtime_transport(tmp_path,[]))
    host = EngineeringHarnessHost(
        workspace=tmp_path,
        process_config=_process(tmp_path),
        engineering_os_base_url="http://engineering-os",
        scope_client=EngineeringOSScopeClient("http://engineering-os",client=os_http),
        tool_client=EngineeringOSToolClient("http://engineering-os",client=os_http),
        bootstrap_client=ToolRuntimeBootstrapClient("http://tool-runtime",client=rt_http),
        allow_publish=False,
    )
    try:
        await host.prepare("work")
        assert host.runtime is not None
        assert "OPENWORKER_ENGINEERING_ALLOW_PUBLISH" not in host.runtime.process_config.env
    finally:
        await host.aclose(); os_http.close(); rt_http.close()
