from __future__ import annotations

import json
from pathlib import Path

from coworker.case_worklist import CaseStep, CaseWorklist, CaseWorklistStore, StepStatus
from scripts.case_worklist_sync_manifest import sync_manifest


def test_sync_manifest_preserves_passed_steps_and_inserts_new_gate(tmp_path):
    workspace = tmp_path / "0002"
    workspace.mkdir()
    store = CaseWorklistStore(workspace)
    current = CaseWorklist(
        case_id="0002",
        workspace_root=str(workspace),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[
            CaseStep(step_id="0002-010", title="director", allowed_actions=["director"], acceptance=["receipt"]),
            CaseStep(step_id="0002-020", title="storyboard", dependencies=["0002-010"], allowed_actions=["storyboard"], acceptance=["request"]),
            CaseStep(step_id="0002-030", title="images", dependencies=["0002-020"], allowed_actions=["image"]),
        ],
    )
    current.start("0002-010", "director")
    current.record_evidence("0002-010", "receipt", "director.json")
    current.pass_step("0002-010")
    current.start("0002-020", "storyboard")
    current.record_evidence("0002-020", "request", "storyboard.json")
    current.pass_step("0002-020")
    store.save(current)

    manifest = {
        "schema_version": "openworker-case-worklist/v1",
        "case_id": "0002",
        "workspace_root": str(workspace),
        "assigned_host": "DESKTOP-ODAQN0D",
        "revision": 2,
        "steps": [
            {"step_id": "0002-010", "title": "director", "dependencies": [], "allowed_actions": ["director"], "acceptance": ["receipt"]},
            {"step_id": "0002-020", "title": "storyboard", "dependencies": ["0002-010"], "allowed_actions": ["storyboard"], "acceptance": ["request"]},
            {"step_id": "0002-025", "title": "text pptx", "dependencies": ["0002-020"], "allowed_actions": ["presentation.openmaic"], "acceptance": ["pptx"]},
            {"step_id": "0002-027", "title": "user approval", "kind": "approval", "dependencies": ["0002-025"], "allowed_actions": ["openworker.user.approval"], "acceptance": ["decision"]},
            {"step_id": "0002-030", "title": "images", "dependencies": ["0002-027"], "allowed_actions": ["image"], "acceptance": []},
        ],
    }
    manifest_path = tmp_path / "0002.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    synced = sync_manifest(workspace, manifest_path)
    assert synced.step("0002-010").status == StepStatus.PASSED
    assert synced.step("0002-010").evidence["receipt"] == "director.json"
    assert synced.step("0002-020").status == StepStatus.PASSED
    assert synced.step("0002-025").status == StepStatus.READY
    assert synced.step("0002-027").status == StepStatus.PENDING
    assert synced.step("0002-030").status == StepStatus.PENDING
    assert synced.next_step().step_id == "0002-025"
