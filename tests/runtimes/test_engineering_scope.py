from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from coworker.runtimes.engineering_scope import (
    EngineeringOSScopeClient,
    EngineeringScopeError,
    workspace_project_code,
)


def test_scope_reuses_deterministic_workspace_project_and_creates_fresh_job(tmp_path: Path) -> None:
    seen: list[tuple[str, str, dict | None]] = []
    projects: list[dict] = []
    jobs: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/api/v1/projects":
            return httpx.Response(200, json={"items": projects})
        if request.method == "POST" and request.url.path == "/api/v1/projects":
            created = {"id": "prj-1", **body}
            projects.append(created)
            return httpx.Response(201, json=created)
        if request.method == "POST" and request.url.path == "/api/v1/jobs":
            created = {"id": f"job-{len(jobs)+1}", **body}
            jobs.append(created)
            return httpx.Response(201, json=created)
        return httpx.Response(404, json={"error": "not_found"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = EngineeringOSScopeClient("http://engineering-os", client=http)
        first = client.ensure(tmp_path, "first task")
        second = client.ensure(tmp_path, "second task")

    assert first.project_id == second.project_id == "prj-1"
    assert first.project_code == second.project_code == workspace_project_code(tmp_path)
    assert first.job_id == "job-1"
    assert second.job_id == "job-2"
    assert first.job_code != second.job_code
    project_posts = [item for item in seen if item[:2] == ("POST", "/api/v1/projects")]
    job_posts = [item for item in seen if item[:2] == ("POST", "/api/v1/jobs")]
    assert len(project_posts) == 1
    assert len(job_posts) == 2
    assert job_posts[0][2]["project_id"] == "prj-1"
    assert job_posts[0][2]["metadata"]["workspace_root"] == str(tmp_path.resolve())
    assert job_posts[1][2]["user_request"] == "second task"


def test_scope_project_code_changes_with_workspace_identity(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert workspace_project_code(a) == workspace_project_code(a)
    assert workspace_project_code(a) != workspace_project_code(b)
    assert workspace_project_code(a).startswith("OW-")


def test_scope_fails_closed_on_ambiguous_project_code(tmp_path: Path) -> None:
    code = workspace_project_code(tmp_path)
    payload = {"items": [{"id":"p1","code":code},{"id":"p2","code":code.lower()}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=payload))) as http:
        client = EngineeringOSScopeClient("http://engineering-os", client=http)
        with pytest.raises(EngineeringScopeError, match="ambiguous"):
            client.ensure(tmp_path, "work")


def test_scope_fails_closed_on_os_error(tmp_path: Path) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(503, json={"error":"down"}))) as http:
        client = EngineeringOSScopeClient("http://engineering-os", client=http)
        with pytest.raises(EngineeringScopeError, match="503"):
            client.ensure(tmp_path, "work")
