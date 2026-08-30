from __future__ import annotations

from coworker.review_cycle import ReviewArtifact, ReviewCycle
from coworker.work_ledger import WorkLedger


def test_llm_tune_creates_native_tuning_revision(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code="OWJ-TUNING-KIND", title="native tuning kind", workspace=str(workspace))
    revision_id = work["head_revision_id"]
    ledger.set_revision_status(revision_id, "verifying")
    artifact = workspace / "render.png"
    artifact.write_bytes(b"render")
    cycle = ReviewCycle(workspace)
    cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("render", artifact)],
        review_dimensions=["framing"],
        current_parameters={"camera_height": 12.0},
        allowed_parameter_keys=["camera_height"],
        capability_id="scenex.render",
        owning_repo="liuxb99/SceneX",
    )

    result = cycle.apply_receipt(
        ledger,
        revision_id,
        {
            "verdict": "TUNE",
            "summary": "move camera closer",
            "parameter_changes": [
                {
                    "parameter": "camera_height",
                    "before": 12.0,
                    "after": 9.0,
                    "reason": "bridge too small",
                    "expected_effect": "larger bridge framing",
                }
            ],
        },
        allowed_parameter_keys=["camera_height"],
        current_parameters={"camera_height": 12.0},
    )

    child = ledger.get_revision(result["next_revision_id"])
    assert child["kind"] == "tuning"
    assert child["parent_revision_id"] == revision_id
    assert child["plan"]["revision_role"] == "tuning"
    assert child["plan"]["source_review_revision_id"] == revision_id
    ledger.close()
