import json
from pathlib import Path

from coworker.case_controller import LocalCaseController
from coworker.case_worklist import CaseStep, CaseWorklist, CaseWorklistStore, StepStatus


class FakeNode:
    def __init__(self):
        self.submitted = []

    def node_status(self):
        return {"machine": "DESKTOP-ODAQN0D", "online": True, "max_workers": 4}

    def submit(self, payload):
        self.submitted.append(payload)
        return {
            "job_id": payload["job_id"],
            "dispatch_id": payload["dispatch_id"],
            "machine": payload["machine"],
            "accepted": True,
            "queue_position": 1,
            "duplicate": False,
        }


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_bootstrap_dispatches_one_local_durable_job_without_github(tmp_path: Path):
    workspace = tmp_path / "case"
    manifest_path = tmp_path / "manifest.json"
    spec_path = tmp_path / "spec.json"
    write_json(
        manifest_path,
        {
            "schema_version": "openworker-case-worklist/v1",
            "case_id": "0005",
            "workspace_root": str(workspace),
            "assigned_host": "DESKTOP-ODAQN0D",
            "steps": [
                {
                    "step_id": "0005-010",
                    "title": "director",
                    "kind": "work",
                    "dependencies": [],
                    "allowed_actions": ["comfyx-studio.director.preproduction"],
                    "acceptance": ["run_id"],
                    "status": "PENDING",
                }
            ],
        },
    )
    write_json(spec_path, {"case_id": "0005", "title": "Snow White", "source_story": "story"})

    controller = LocalCaseController(workspace)
    fake = FakeNode()
    controller.node = fake
    result = controller.bootstrap(manifest_path, spec_path)

    assert len(fake.submitted) == 1
    payload = fake.submitted[0]
    assert payload["machine"] == "DESKTOP-ODAQN0D"
    assert payload["dispatch_id"].startswith("local-controller-")
    assert "github" not in payload["command"].lower()
    assert result["github_action_used_for_business_execution"] is False
    assert result["dispatched"][0]["durable_ack"]["accepted"] is True

    persisted = CaseWorklistStore(workspace).load()
    assert persisted.step("0005-010").status == StepStatus.RUNNING


def test_approval_frontier_is_attention_not_auto_execution(tmp_path: Path):
    workspace = tmp_path / "case"
    workspace.mkdir()
    worklist = CaseWorklist(
        case_id="0005",
        workspace_root=str(workspace),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[
            CaseStep(
                step_id="0005-027",
                title="approval",
                kind="approval",
                allowed_actions=["openworker.user.approval"],
                acceptance=["approval_decision"],
            )
        ],
    )
    CaseWorklistStore(workspace).save(worklist)
    write_json(workspace / ".openworker" / "case-spec.json", {"case_id": "0005"})

    controller = LocalCaseController(workspace)
    fake = FakeNode()
    controller.node = fake
    result = controller.dispatch_ready()

    assert fake.submitted == []
    assert result["attention"] == [
        {"step_id": "0005-027", "reason": "user_approval_required", "title": "approval"}
    ]
