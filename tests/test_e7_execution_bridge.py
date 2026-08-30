from __future__ import annotations

import pytest

from coworker.personas.execution_bridge import (
    ExecutionBridgeError,
    UnsupportedCanonicalFlowError,
    media_submit_tool_call,
    rc_column_tool_call,
    read_canonical_result,
)
from coworker.personas.submission import PersonaJobSubmission


def _submission(*, capability: str = "engineering") -> PersonaJobSubmission:
    return PersonaJobSubmission(
        project_id="project-1",
        job_id="job-1",
        reused=False,
        task_package_path=".openworker/persona-tasks/company/s1/pkg.json",
        persona="company",
        session_id="s1",
        handoff_capabilities=(capability,),
    )


class FakeReader:
    def __init__(self) -> None:
        self.job = {
            "id": "job-1",
            "project_id": "project-1",
            "status": "review",
            "revision": 3,
            "metadata": {
                "persona": "company",
                "persona_session_id": "s1",
                "task_package_path": ".openworker/persona-tasks/company/s1/pkg.json",
            },
        }
        self.artifacts = [{
            "id": "artifact-1",
            "project_id": "project-1",
            "job_id": "job-1",
            "kind": "report",
            "uri": "workspace://deliverables/report.pdf",
            "media_type": "application/pdf",
            "checksum": "sha256:abc",
        }]
        self.reviews = [{"id": "review-1", "job_id": "job-1", "decision": "approved"}]
        self.approval = {"job_id": "job-1", "approved": True}

    def get_job(self, job_id):
        assert job_id == "job-1"
        return dict(self.job)

    def list_job_artifacts(self, job_id):
        assert job_id == "job-1"
        return [dict(item) for item in self.artifacts]

    def list_job_reviews(self, job_id):
        assert job_id == "job-1"
        return [dict(item) for item in self.reviews]

    def approval_status(self, job_id):
        assert job_id == "job-1"
        return dict(self.approval)


def test_rc_column_descriptor_targets_existing_tool_and_preserves_approval_gate():
    call = rc_column_tool_call(_submission(), {"component_id": "C1", "width_mm": 400})
    data = call.to_dict()
    assert data["tool_name"] == "engineering_execute_rc_column_flow"
    assert data["arguments"]["job_id"] == "job-1"
    assert data["requires_approval"] is True
    assert data["authority"] == "AI-Engineering-OS"
    assert data["execution"] == "not-performed"


def test_rc_column_descriptor_rejects_non_engineering_submission():
    with pytest.raises(UnsupportedCanonicalFlowError, match="engineering capability"):
        rc_column_tool_call(_submission(capability="media"), {"component_id": "C1"})


def test_media_submit_descriptor_targets_vetted_comfyx_facade_and_preserves_approval_gate():
    call = media_submit_tool_call(
        _submission(capability="media"),
        {"prompt": "cinematic bridge", "modelMode": "FL2VA", "durationSeconds": 6},
    )
    data = call.to_dict()
    assert data["tool_name"] == "engineering_generate_minimax_h3"
    assert data["arguments"]["prompt"] == "cinematic bridge"
    assert data["requires_approval"] is True
    assert data["authority"] == "AI-Engineering-OS"
    assert data["execution"] == "not-performed"


def test_media_submit_rejects_non_media_submission_and_compile_only():
    with pytest.raises(UnsupportedCanonicalFlowError, match="media capability"):
        media_submit_tool_call(_submission(), {"prompt": "video"})
    with pytest.raises(ExecutionBridgeError, match="compile_only"):
        media_submit_tool_call(_submission(capability="media"), {"prompt": "video", "compile_only": True})


def test_result_snapshot_reads_existing_job_artifact_review_and_approval_identity():
    result = read_canonical_result(FakeReader(), _submission())
    data = result.to_dict()
    assert data["status"] == "review"
    assert data["job"]["identifier"] == "job-1"
    assert data["artifacts"][0]["identifier"] == "artifact-1"
    assert data["artifacts"][0]["checksum"] == "sha256:abc"
    assert data["reviews"][0]["id"] == "review-1"
    assert data["approved"] is True
    assert data["publish_performed"] is False
    assert data["external_send_performed"] is False


def test_result_snapshot_rejects_job_lineage_mismatch():
    reader = FakeReader()
    reader.job["metadata"]["persona_session_id"] = "other"
    with pytest.raises(ExecutionBridgeError, match="lineage mismatch"):
        read_canonical_result(reader, _submission())


def test_result_snapshot_rejects_cross_job_review():
    reader = FakeReader()
    reader.reviews = [{"id": "review-2", "job_id": "job-other", "decision": "approved"}]
    with pytest.raises(ExecutionBridgeError, match="different Job"):
        read_canonical_result(reader, _submission())


def test_result_snapshot_requires_boolean_canonical_approval():
    reader = FakeReader()
    reader.approval = {"approved": "yes"}
    with pytest.raises(ExecutionBridgeError, match="approved boolean"):
        read_canonical_result(reader, _submission())
