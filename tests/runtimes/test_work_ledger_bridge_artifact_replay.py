from __future__ import annotations

from types import SimpleNamespace

import pytest

from coworker.runtimes.job_binding import JobBinding
from coworker.runtimes.work_ledger_bridge import WorkLedgerBridge
from coworker.work_ledger import WorkLedgerError


def _binding(workspace):
    return JobBinding(
        schema_version="openworker.job-binding.v1",
        assigned_host="TEST-HOST",
        workspace_root=str(workspace),
        project_id="prj_test",
        project_code="OW-TEST",
        job_id="job_test",
        job_code="OWJ-TEST-ARTIFACT-REPLAY",
    )


def _event(event_id: str, artifact_name: str):
    return SimpleNamespace(
        event_id=event_id,
        kind="progress",
        status="running",
        summary="artifact replay fixture",
        details={},
        artifact_refs=(artifact_name,),
        capability_id="test.artifact.replay",
        runtime_job_id="runtime-test",
    )


def test_same_artifact_identity_is_idempotent_within_revision(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "result.json"
    artifact.write_text('{"value":1}', encoding="utf-8")
    binding = _binding(workspace)
    bridge = WorkLedgerBridge(workspace)
    bridge.ensure(binding)

    first = bridge.sync_project_event(binding, _event("evt-1", "result.json"))
    second = bridge.sync_project_event(binding, _event("evt-2", "result.json"))

    revision_id = first["work"]["head_revision_id"]
    first_revision = next(item for item in first["revisions"] if item["revision_id"] == revision_id)
    second_revision = next(item for item in second["revisions"] if item["revision_id"] == revision_id)
    assert len(first_revision["artifacts"]) == 1
    assert len(second_revision["artifacts"]) == 1
    assert first_revision["artifacts"][0]["sha256"] == second_revision["artifacts"][0]["sha256"]
    assert first_revision["artifacts"][0]["size_bytes"] == second_revision["artifacts"][0]["size_bytes"]
    assert first_revision["artifacts"][0]["path"] == second_revision["artifacts"][0]["path"]


def test_changed_bytes_under_same_logical_name_fail_closed(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "result.json"
    artifact.write_text('{"value":1}', encoding="utf-8")
    binding = _binding(workspace)
    bridge = WorkLedgerBridge(workspace)
    bridge.ensure(binding)
    before = bridge.sync_project_event(binding, _event("evt-1", "result.json"))

    artifact.write_text('{"value":2,"changed":true}', encoding="utf-8")
    with pytest.raises(WorkLedgerError, match="ARTIFACT_REPLAY_CONFLICT"):
        bridge.sync_project_event(binding, _event("evt-2", "result.json"))

    after = bridge.snapshot(binding)
    revision_id = before["work"]["head_revision_id"]
    revision = next(item for item in after["revisions"] if item["revision_id"] == revision_id)
    assert len(revision["artifacts"]) == 1
    assert revision["artifacts"][0]["sha256"] == next(
        item for item in before["revisions"] if item["revision_id"] == revision_id
    )["artifacts"][0]["sha256"]
