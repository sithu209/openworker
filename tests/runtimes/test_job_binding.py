from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker.runtimes.engineering_scope import EngineeringScope
from coworker.runtimes.job_binding import JobBindingError, JobBindingStore
from coworker.runtimes.work_ledger_bridge import WorkLedgerBridge


def test_job_binding_persists_host_workspace_and_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-A")
    scope = EngineeringScope("prj-1", "CASE-0002", "job-1", "0002-ALADDIN")
    store = JobBindingStore(tmp_path)

    created = store.create(scope)
    loaded = store.load()

    assert loaded == created
    assert loaded is not None
    assert loaded.assigned_host == "DESKTOP-A"
    assert Path(loaded.workspace_root) == tmp_path.resolve()
    assert loaded.scope() == scope
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "openworker.job-binding.v1"

    ledger_path = tmp_path / ".openworker" / "work-ledger.sqlite"
    assert ledger_path.is_file()
    snapshot = WorkLedgerBridge(tmp_path).snapshot(loaded)
    assert snapshot["schema"] == "openworker-work-ledger/v1"
    assert snapshot["work"]["code"] == "0002-ALADDIN"
    assert snapshot["work"]["workspace"] == str(tmp_path.resolve())
    assert len(snapshot["revisions"]) == 1
    assert snapshot["revisions"][0]["kind"] == "initial"


def test_job_binding_fails_closed_on_other_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-A")
    store = JobBindingStore(tmp_path)
    store.create(EngineeringScope("prj-1", "P", "job-1", "J"))

    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-B")
    with pytest.raises(JobBindingError, match="assigned to host DESKTOP-A"):
        store.load()


def test_work_ledger_bridge_tracks_physical_artifact_and_rework(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-A")
    binding = JobBindingStore(tmp_path).create(
        EngineeringScope("prj-3", "CASE-0003", "job-3", "0003-YUJING-BRIDGE")
    )
    bridge = WorkLedgerBridge(tmp_path)

    artifact = tmp_path / "terrain-render.png"
    artifact.write_bytes(b"real-render-evidence")
    recorded = bridge.add_file_artifact(
        binding,
        logical_name="terrain-render",
        path=artifact,
        provenance={"capability_id": "terrain.blender.execute", "runner": "DESKTOP-A"},
    )
    assert recorded["size_bytes"] == len(b"real-render-evidence")
    assert recorded["verification_status"] == "passed"

    failed = bridge.require_rework(
        binding,
        reason="SceneX reopen verification failed",
        gap_owner_repo="liuxb99/SceneX",
        changed_contracts=["scenex.region.reopen"],
        verification_plan=["rerun real Godot reopen"],
    )
    assert failed["status"] == "rework_required"
    assert failed["gap_owner_repo"] == "liuxb99/SceneX"

    child = bridge.open_rework(binding, goal="repair SceneX reopen")
    assert child["kind"] == "rework"
    assert child["revision_no"] == 2
    assert child["rework_of_revision_id"] == failed["revision_id"]

    snapshot = bridge.snapshot(binding)
    assert len(snapshot["revisions"]) == 2
    assert snapshot["revisions"][0]["artifacts"][0]["logical_name"] == "terrain-render"
    assert snapshot["revisions"][0]["status"] == "rework_required"
    assert snapshot["revisions"][1]["parent_revision_id"] == snapshot["revisions"][0]["revision_id"]


def test_resume_replays_project_knowledge_failure_and_repair_into_revisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-A")
    store = JobBindingStore(tmp_path)
    binding = store.create(EngineeringScope("prj-3", "CASE-0003", "job-3", "0003-YUJING-BRIDGE"))
    root = tmp_path / ".openworker"
    events = root / "project-knowledge.jsonl"

    failure = {
        "schema_version": "openworker.project-knowledge-event.v1",
        "sequence": 1,
        "timestamp": "2026-08-17T00:00:00+00:00",
        "project_id": "prj-3",
        "job_id": "job-3",
        "kind": "failed",
        "stage": "final-acceptance",
        "summary": "SceneX reopen verification failed",
        "status": "failed",
        "owner": "OpenWorker",
        "capability_id": "scenex.region.reopen",
        "evidence": [],
        "blockers": ["SceneX reopen failed"],
        "decisions": [],
        "next_actions": ["repair SceneX"],
        "details": {
            "gap_owner_repo": "liuxb99/SceneX",
            "changed_contracts": ["scenex.region.reopen"],
            "verification_plan": ["rerun REAL reopen"],
        },
        "event_id": "evt-fail",
        "runtime": "github-actions",
        "session_id": "",
        "runtime_job_id": "951",
        "execution_id": "",
        "prompt_id": "",
        "artifact_refs": [],
        "artifact_disposition": "",
    }
    events.write_text(json.dumps(failure) + "\n", encoding="utf-8")

    # Loading/resuming the fixed job replays unsynced history before returning.
    store.load()
    snapshot = WorkLedgerBridge(tmp_path).snapshot(binding)
    assert snapshot["revisions"][0]["status"] == "rework_required"
    assert snapshot["revisions"][0]["gap_owner_repo"] == "liuxb99/SceneX"

    repair = dict(failure)
    repair.update(
        sequence=2,
        kind="progress",
        status="running",
        summary="repair SceneX and rerun",
        event_id="evt-repair",
        blockers=[],
        details={},
    )
    with events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(repair) + "\n")

    store.load()
    snapshot = WorkLedgerBridge(tmp_path).snapshot(binding)
    assert len(snapshot["revisions"]) == 2
    assert snapshot["revisions"][0]["status"] == "rework_required"
    assert snapshot["revisions"][1]["kind"] == "rework"
    assert snapshot["revisions"][1]["parent_revision_id"] == snapshot["revisions"][0]["revision_id"]
    assert snapshot["revisions"][1]["status"] == "executing"

    # Repeated resumes are idempotent: already-projected events do not fork again.
    store.load()
    again = WorkLedgerBridge(tmp_path).snapshot(binding)
    assert len(again["revisions"]) == 2
    synced_lines = (root / "work-ledger-project-events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(synced_lines) == 2
