from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coworker.personas.product_contract import PersonaSession, build_product_plan
from coworker.personas.submission import (
    SubmissionContractError,
    assess_delivery_readiness,
    collect_job_artifacts,
    submit_product_plan,
)
from coworker.personas.task_package import company_task_package, media_task_package


class FakeEngineeringOSClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.artifacts: dict[str, list[dict[str, Any]]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.publish_calls = 0

    def create_job(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(dict(kwargs))
        job = {
            "id": f"job-{len(self.created)}",
            "project_id": kwargs["project_id"],
            "metadata": dict(kwargs.get("metadata") or {}),
            "revision": 1,
        }
        self.jobs[job["id"]] = job
        return job

    def get_job(self, job_id: str) -> dict[str, Any]:
        return dict(self.jobs[job_id])

    def list_job_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.artifacts.get(job_id, [])]

    def approval_status(self, job_id: str) -> dict[str, Any]:
        return dict(self.approvals.get(job_id, {"approved": False, "job_id": job_id}))

    def publish_job(self, **_: Any) -> dict[str, Any]:
        self.publish_calls += 1
        raise AssertionError("E7.4 must never call publish_job")


def _media_plan(tmp_path: Path):
    package = media_task_package(
        title="Launch clip",
        brief="Create an approved launch clip.",
        deliverables=["final.mp4"],
        publish_target="social:brand",
    )
    plan = build_product_plan(
        tmp_path,
        PersonaSession(persona="media", session_id="s-media", workspace_id="project-workspace"),
        package,
        package_id="launch",
    )
    return package, plan


def test_submit_creates_canonical_job_with_persona_lineage(tmp_path: Path) -> None:
    client = FakeEngineeringOSClient()
    package, plan = _media_plan(tmp_path)

    result = submit_product_plan(
        client,
        plan,
        package,
        project_id="project-1",
        job_code="MEDIA-001",
    )

    assert result.job_id == "job-1"
    assert result.reused is False
    assert result.handoff_capabilities == ("media",)
    assert result.to_dict()["authority"] == "AI-Engineering-OS"
    assert result.to_dict()["external_action_performed"] is False

    request = client.created[0]
    assert request["project_id"] == "project-1"
    assert request["name"] == "Launch clip"
    assert request["user_request"] == "Create an approved launch clip."
    assert request["expected_deliverables"] == ["final.mp4"]
    assert request["metadata"]["persona"] == "media"
    assert request["metadata"]["persona_session_id"] == "s-media"
    assert request["metadata"]["task_package_path"] == plan.task_package_path
    assert request["metadata"]["runtime_policy"].startswith("NativeRuntime default")
    assert client.publish_calls == 0


def test_company_submission_requires_at_least_one_canonical_handoff(tmp_path: Path) -> None:
    client = FakeEngineeringOSClient()
    package = company_task_package(title="Internal brief", brief="Prepare only a local brief.")
    plan = build_product_plan(
        tmp_path,
        PersonaSession(persona="company", session_id="s1", workspace_id="w1"),
        package,
        package_id="brief",
    )

    with pytest.raises(SubmissionContractError, match="no canonical handoff"):
        submit_product_plan(client, plan, package, project_id="p1", job_code="C-1")
    assert client.created == []


def test_job_reuse_is_explicit_and_validates_project_and_persona_lineage(tmp_path: Path) -> None:
    client = FakeEngineeringOSClient()
    package, plan = _media_plan(tmp_path)
    client.jobs["job-existing"] = {
        "id": "job-existing",
        "project_id": "project-1",
        "metadata": {
            "persona": "media",
            "persona_session_id": "s-media",
            "workspace_id": "project-workspace",
            "task_package_path": plan.task_package_path,
        },
    }

    reused = submit_product_plan(
        client,
        plan,
        package,
        project_id="project-1",
        job_code="MEDIA-001",
        existing_job_id="job-existing",
    )
    assert reused.reused is True
    assert reused.job_id == "job-existing"
    assert client.created == []

    client.jobs["job-wrong-project"] = {
        "id": "job-wrong-project",
        "project_id": "project-2",
        "metadata": {},
    }
    with pytest.raises(SubmissionContractError, match="different project"):
        submit_product_plan(
            client,
            plan,
            package,
            project_id="project-1",
            job_code="MEDIA-001",
            existing_job_id="job-wrong-project",
        )

    client.jobs["job-wrong-session"] = {
        "id": "job-wrong-session",
        "project_id": "project-1",
        "metadata": {"persona_session_id": "another-session"},
    }
    with pytest.raises(SubmissionContractError, match="metadata mismatch"):
        submit_product_plan(
            client,
            plan,
            package,
            project_id="project-1",
            job_code="MEDIA-001",
            existing_job_id="job-wrong-session",
        )


def test_real_canonical_artifacts_are_converted_to_existing_evidence_refs() -> None:
    client = FakeEngineeringOSClient()
    client.artifacts["job-1"] = [
        {
            "id": "artifact-1",
            "project_id": "project-1",
            "job_id": "job-1",
            "kind": "video",
            "uri": "workspace://deliverables/final.mp4",
            "media_type": "video/mp4",
            "checksum": "sha256:abc",
            "source_run_id": "run-1",
        }
    ]

    refs = collect_job_artifacts(client, "job-1")
    assert len(refs) == 1
    assert refs[0].system == "ai-engineering-os"
    assert refs[0].identifier == "artifact-1"
    assert refs[0].checksum == "sha256:abc"
    assert refs[0].metadata["job_id"] == "job-1"


def test_delivery_ready_requires_both_qa_and_canonical_approval() -> None:
    client = FakeEngineeringOSClient()
    client.artifacts["job-1"] = [
        {
            "id": "artifact-1",
            "project_id": "project-1",
            "job_id": "job-1",
            "kind": "report",
            "uri": "workspace://deliverables/report.pdf",
            "media_type": "application/pdf",
            "checksum": "sha256:def",
        }
    ]

    client.approvals["job-1"] = {"approved": False, "reason": "review pending"}
    pending = assess_delivery_readiness(client, "job-1", qa_passed=True, qa_notes=["opens"])
    assert pending.evidence.qa_status.value == "passed"
    assert pending.evidence.delivery_ready is False
    assert pending.approved is False

    client.approvals["job-1"] = {"approved": True, "reason": "all current revisions approved"}
    ready = assess_delivery_readiness(client, "job-1", qa_passed=True, qa_notes=["opens"])
    data = ready.to_dict()
    assert data["approved"] is True
    assert data["evidence"]["delivery_ready"] is True
    assert data["publish_performed"] is False
    assert data["external_send_performed"] is False
    assert client.publish_calls == 0


def test_passed_qa_without_real_artifact_fails_closed() -> None:
    client = FakeEngineeringOSClient()
    client.approvals["job-empty"] = {"approved": True}
    with pytest.raises(SubmissionContractError, match="at least one real artifact"):
        assess_delivery_readiness(client, "job-empty", qa_passed=True)
