from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from coworker.engineering.source_ingress import EngineeringSourceIngress, SourceIngressError


class FakeOS:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "os-jobs"
        self.root.mkdir()
        self.project = {"id": "prj_1", "code": "OW-TEST", "name": "test"}
        self.job = {
            "id": "job_1",
            "project_id": "prj_1",
            "code": "OWJ-TEST",
            "name": "run",
            "working_dir": str(self.root / "job_1" / "working"),
            "delivery_dir": str(self.root / "job_1" / "delivery"),
        }
        Path(self.job["working_dir"]).mkdir(parents=True)
        Path(self.job["delivery_dir"]).mkdir(parents=True)
        self.inputs: list[dict] = []
        self.artifacts: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        if method == "GET" and path == "/api/v1/projects":
            return httpx.Response(200, json={"items": []})
        if method == "POST" and path == "/api/v1/projects":
            return httpx.Response(201, json=self.project)
        if method == "POST" and path == "/api/v1/jobs":
            return httpx.Response(201, json=self.job)
        if method == "GET" and path == "/api/v1/jobs/job_1":
            return httpx.Response(200, json=self.job)
        if method == "GET" and path == "/api/v1/jobs/job_1/inputs":
            return httpx.Response(200, json={"items": self.inputs})
        if method == "POST" and path == "/api/v1/jobs/job_1/inputs":
            body = json.loads(request.content)
            import base64
            data = base64.b64decode(body["content_base64"])
            dest = Path(self.job["working_dir"]) / "01-原始資料" / body["file_name"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            item = {
                "id": f"inp_{len(self.inputs)+1}",
                "job_id": "job_1",
                "original_name": body["file_name"],
                "stored_name": body["file_name"],
                "relative_path": f"working/01-原始資料/{body['file_name']}",
                "media_type": body["media_type"],
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            self.inputs.append(item)
            return httpx.Response(201, json=item)
        if method == "GET" and path == "/api/v1/projects/prj_1/artifacts":
            return httpx.Response(200, json={"items": self.artifacts})
        if method == "POST" and path == "/api/v1/projects/prj_1/artifacts":
            body = json.loads(request.content)
            item = {"id": f"art_{len(self.artifacts)+1}", "revision": 1, **body, "project_id": "prj_1"}
            self.artifacts.append(item)
            return httpx.Response(201, json=item)
        return httpx.Response(404, json={"error": "not_found", "path": path})


def client_for(fake: FakeOS) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake.handler), base_url="http://os")


def test_ingress_materializes_imports_registers_and_retries_idempotently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-O87PJNR")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "real.dwg"
    source.write_bytes(b"AC1032\x00real-engineering-dwg")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    fake = FakeOS(tmp_path)
    client = client_for(fake)

    ingress = EngineeringSourceIngress(
        os_url="http://os",
        workspace=workspace,
        assigned_host="DESKTOP-O87PJNR",
        user_request="DWG to 3D",
        client=client,
    )
    first = ingress.ingest(
        source,
        canonical_name="source.dwg",
        original_name="user.dwg",
        expected_size=source.stat().st_size,
        expected_sha256=digest,
        expected_header="AC1032",
        source_run_id="run-1",
        producer_repository="liuxb99/openworker",
        producer_commit_sha="a" * 40,
    )
    second = ingress.ingest(
        source,
        canonical_name="source.dwg",
        original_name="user.dwg",
        expected_size=source.stat().st_size,
        expected_sha256=digest,
        expected_header="AC1032",
        source_run_id="run-1",
        producer_repository="liuxb99/openworker",
        producer_commit_sha="a" * 40,
    )

    assert Path(first.canonical_path).read_bytes() == source.read_bytes()
    assert first.os_input_id == "inp_1"
    assert first.os_artifact_id == "art_1"
    assert not first.already_materialized
    assert not first.already_imported
    assert not first.already_registered
    assert second.already_materialized
    assert second.already_imported
    assert second.already_registered
    assert len(fake.inputs) == 1
    assert len(fake.artifacts) == 1
    provenance = json.loads((workspace / "input" / "source-provenance.json").read_text(encoding="utf-8"))
    assert provenance["sha256"] == digest
    binding = json.loads((workspace / ".openworker" / "job-binding.json").read_text(encoding="utf-8"))
    assert binding["assigned_host"] == "DESKTOP-O87PJNR"
    knowledge = (workspace / ".openworker" / "project-knowledge.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(knowledge) == 2


def test_ingress_rejects_wrong_host_before_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-OTHER")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "real.dwg"
    source.write_bytes(b"AC1032\x00real")
    fake = FakeOS(tmp_path)
    ingress = EngineeringSourceIngress(
        os_url="http://os",
        workspace=workspace,
        assigned_host="DESKTOP-O87PJNR",
        user_request="DWG to 3D",
        client=client_for(fake),
    )
    with pytest.raises(SourceIngressError, match="assigned host"):
        ingress.ingest(source)
    assert not (workspace / ".openworker").exists()
    assert not fake.inputs


def test_ingress_refuses_to_overwrite_different_canonical_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-O87PJNR")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "real.dwg"
    source.write_bytes(b"AC1032\x00one")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    fake = FakeOS(tmp_path)
    ingress = EngineeringSourceIngress(
        os_url="http://os",
        workspace=workspace,
        assigned_host="DESKTOP-O87PJNR",
        user_request="DWG to 3D",
        client=client_for(fake),
    )
    ingress.ingest(source, expected_sha256=digest, expected_header="AC1032")
    source.write_bytes(b"AC1032\x00two")
    with pytest.raises(SourceIngressError, match="different SHA256"):
        ingress.ingest(source, expected_header="AC1032")
