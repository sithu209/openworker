from __future__ import annotations

import json

import pytest

from coworker.case_worklist import (
    CaseStep,
    CaseWorklist,
    CaseWorklistError,
    CaseWorklistStore,
    StepStatus,
)


def build_worklist(tmp_path):
    workspace = tmp_path / "0004"
    workspace.mkdir()
    return CaseWorklist(
        case_id="0004",
        workspace_root=str(workspace),
        assigned_host="DESKTOP-O87PJNR",
        steps=[
            CaseStep(
                step_id="0004-010",
                title="Locate exact DWG on O87",
                allowed_actions=["openworker.source.locate", "openworker.source.verify"],
                acceptance=["run_id", "source_path", "sha256"],
            ),
            CaseStep(
                step_id="0004-020",
                title="Canonical source ingress",
                dependencies=["0004-010"],
                allowed_actions=["openworker.source.ingress"],
                acceptance=["job_id", "canonical_path", "sha256"],
            ),
            CaseStep(
                step_id="0004-030",
                title="Open DWG",
                dependencies=["0004-020"],
                allowed_actions=["cad.open_dwg"],
                acceptance=["run_id", "receipt"],
            ),
        ],
    )


def test_only_manifest_first_step_is_canonical_next(tmp_path):
    worklist = build_worklist(tmp_path)
    assert worklist.next_step().step_id == "0004-010"
    assert worklist.step("0004-010").status == StepStatus.READY
    assert worklist.step("0004-020").status == StepStatus.PENDING


def test_running_multi_action_step_remains_canonical(tmp_path):
    worklist = build_worklist(tmp_path)
    worklist.start("0004-010", "openworker.source.locate")
    assert worklist.next_step().step_id == "0004-010"
    revision = worklist.revision
    worklist.start("0004-010", "openworker.source.verify")
    assert worklist.step("0004-010").status == StepStatus.RUNNING
    assert worklist.revision == revision


def test_future_step_stays_blocked_while_current_step_running(tmp_path):
    worklist = build_worklist(tmp_path)
    worklist.start("0004-010", "openworker.source.locate")
    with pytest.raises(CaseWorklistError, match="case drift blocked"):
        worklist.assert_action_allowed("0004-020", "openworker.source.ingress")


def test_multiple_running_steps_are_rejected_on_load(tmp_path):
    worklist = build_worklist(tmp_path)
    payload = worklist.as_dict()
    payload["steps"][0]["status"] = "RUNNING"
    payload["steps"][1]["status"] = "RUNNING"
    with pytest.raises(CaseWorklistError, match="multiple RUNNING"):
        CaseWorklist.from_dict(payload)


def test_drift_to_later_step_is_fail_closed(tmp_path):
    worklist = build_worklist(tmp_path)
    with pytest.raises(CaseWorklistError, match="case drift blocked"):
        worklist.assert_action_allowed("0004-020", "openworker.source.ingress")


def test_wrong_action_for_current_step_is_fail_closed(tmp_path):
    worklist = build_worklist(tmp_path)
    with pytest.raises(CaseWorklistError, match="not allowed"):
        worklist.assert_action_allowed("0004-010", "cad.open_dwg")


def test_ready_step_cannot_record_evidence_or_pass_without_start(tmp_path):
    worklist = build_worklist(tmp_path)
    with pytest.raises(CaseWorklistError, match="cannot record evidence"):
        worklist.record_evidence("0004-010", "run_id", 123)
    with pytest.raises(CaseWorklistError, match="cannot pass"):
        worklist.pass_step("0004-010")


def test_step_cannot_pass_without_acceptance_evidence(tmp_path):
    worklist = build_worklist(tmp_path)
    worklist.start("0004-010", "openworker.source.locate")
    worklist.record_evidence("0004-010", "run_id", 123)
    with pytest.raises(CaseWorklistError, match="source_path, sha256"):
        worklist.pass_step("0004-010")


def test_pass_advances_to_next_step(tmp_path):
    worklist = build_worklist(tmp_path)
    worklist.start("0004-010", "openworker.source.locate")
    worklist.record_evidence("0004-010", "run_id", 123)
    worklist.record_evidence("0004-010", "source_path", r"D:\source.dwg")
    worklist.record_evidence("0004-010", "sha256", "abc")
    worklist.pass_step("0004-010")
    assert worklist.next_step().step_id == "0004-020"


def test_repair_must_attach_to_blocked_parent_and_returns_to_parent(tmp_path):
    worklist = build_worklist(tmp_path)
    worklist.start("0004-010", "openworker.source.locate")
    worklist.block("0004-010", "O87 label missing")

    repair = worklist.add_repair(
        parent_step_id="0004-010",
        step_id="R-0004-010-001",
        title="Bootstrap O87 runner label",
        allowed_actions=["github.runner_label.bootstrap"],
        acceptance=["bootstrap_run_id"],
    )
    assert repair.status == StepStatus.READY
    assert worklist.next_step().step_id == "R-0004-010-001"

    worklist.start("R-0004-010-001", "github.runner_label.bootstrap")
    worklist.record_evidence("R-0004-010-001", "bootstrap_run_id", 32000326696)
    worklist.pass_step("R-0004-010-001")

    assert worklist.step("0004-010").status == StepStatus.READY
    assert worklist.next_step().step_id == "0004-010"


def test_repair_cannot_be_added_to_unblocked_step(tmp_path):
    worklist = build_worklist(tmp_path)
    with pytest.raises(CaseWorklistError, match="BLOCKED parent"):
        worklist.add_repair(
            parent_step_id="0004-010",
            step_id="R-1",
            title="unnecessary side quest",
            allowed_actions=["anything"],
        )


def test_duplicate_step_id_is_rejected(tmp_path):
    workspace = tmp_path / "dup"
    workspace.mkdir()
    with pytest.raises(CaseWorklistError, match="duplicate step_id"):
        CaseWorklist(
            case_id="x",
            workspace_root=str(workspace),
            assigned_host="HOST",
            steps=[
                CaseStep(step_id="1", title="a"),
                CaseStep(step_id="1", title="b"),
            ],
        )


def test_dependency_cycle_is_rejected(tmp_path):
    workspace = tmp_path / "cycle"
    workspace.mkdir()
    with pytest.raises(CaseWorklistError, match="dependency cycle"):
        CaseWorklist(
            case_id="x",
            workspace_root=str(workspace),
            assigned_host="HOST",
            steps=[
                CaseStep(step_id="1", title="a", dependencies=["2"]),
                CaseStep(step_id="2", title="b", dependencies=["1"]),
            ],
        )


def test_json_round_trip_keeps_authoritative_state(tmp_path):
    worklist = build_worklist(tmp_path)
    store = CaseWorklistStore(worklist.workspace_root)
    path = store.save(worklist)
    assert path.is_file()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "openworker-case-worklist/v1"
    assert raw["canonical_next_step_id"] == "0004-010"

    loaded = store.load()
    assert loaded.case_id == "0004"
    assert loaded.assigned_host == "DESKTOP-O87PJNR"
    assert loaded.next_step().step_id == "0004-010"
    assert loaded.as_dict()["steps"] == worklist.as_dict()["steps"]
