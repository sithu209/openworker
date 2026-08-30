import json

import pytest

from coworker.engineering.engineering_os import EngineeringOSConfig, TransportResponse
from coworker.engineering.project_lifecycle import EngineeringOSProjectClient


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, body, headers, timeout):
        self.calls.append({
            "method": method,
            "url": url,
            "body": body,
            "headers": dict(headers),
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


def response(status, payload):
    return TransportResponse(status=status, body=json.dumps(payload).encode("utf-8"))


def make_client(*responses):
    transport = FakeTransport(responses)
    client = EngineeringOSProjectClient(
        EngineeringOSConfig("http://127.0.0.1:8080", timeout_seconds=3),
        transport=transport,
    )
    return client, transport


def test_create_project_uses_authoritative_os_route():
    client, transport = make_client(response(201, {
        "id": "project-0002",
        "code": "CASE-0002",
        "name": "阿拉丁神燈",
    }))

    project = client.create_project(
        code="CASE-0002",
        name="阿拉丁神燈",
        description="OpenWorker local Action closure case",
        metadata={"case_id": "0002", "source": "openworker"},
    )

    assert project["id"] == "project-0002"
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/api/v1/projects")
    assert json.loads(call["body"]) == {
        "code": "CASE-0002",
        "name": "阿拉丁神燈",
        "description": "OpenWorker local Action closure case",
        "metadata": {"case_id": "0002", "source": "openworker"},
    }


def test_ensure_project_reuses_exact_code_without_mutation():
    client, transport = make_client(response(200, {
        "items": [{"id": "p2", "code": "CASE-0002", "name": "阿拉丁神燈"}]
    }))

    project = client.ensure_project(code="CASE-0002", name="阿拉丁神燈")

    assert project["id"] == "p2"
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"


def test_ensure_project_creates_when_missing():
    client, transport = make_client(
        response(200, {"items": []}),
        response(201, {"id": "p2", "code": "CASE-0002", "name": "阿拉丁神燈"}),
    )

    project = client.ensure_project(code="CASE-0002", name="阿拉丁神燈")

    assert project["id"] == "p2"
    assert [call["method"] for call in transport.calls] == ["GET", "POST"]


def test_ensure_project_rejects_ambiguous_duplicate_codes():
    client, _ = make_client(response(200, {
        "items": [
            {"id": "p1", "code": "CASE-0002"},
            {"id": "p2", "code": "CASE-0002"},
        ]
    }))

    with pytest.raises(RuntimeError, match="multiple"):
        client.ensure_project(code="CASE-0002", name="阿拉丁神燈")
