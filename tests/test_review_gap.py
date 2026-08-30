from __future__ import annotations

import pytest

from coworker.review_cycle import ReviewArtifact, ReviewCycle
from coworker.review_gap import ReviewGapError, apply_review_finding, bundle_manifest_sha256
from coworker.work_ledger import WorkLedger


def _case(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code="OWJ-GAP-1", title="gap fixture", workspace=str(workspace))
    revision_id = work["head_revision_id"]
    ledger.set_revision_status(revision_id, "verifying")
    artifact = workspace / "result.png"
    artifact.write_bytes(b"artifact")
    cycle = ReviewCycle(workspace)
    cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("result", artifact)],
        review_dimensions=["semantic correctness", "tool capability"],
        current_parameters={"camera_height": 10},
        allowed_parameter_keys=["camera_height"],
        capability_id="scenex.terrain.browse",
        owning_repo="liuxb99/SceneX",
    )
    return ledger, cycle, revision_id


def test_tool_gap_enters_rework_required_and_preserves_owner_and_capability(tmp_path):
    ledger, cycle, revision_id = _case(tmp_path)
    result = apply_review_finding(
        cycle,
        ledger,
        revision_id,
        {
            "verdict": "TOOL_GAP",
            "bundle_manifest_sha256": bundle_manifest_sha256(cycle, revision_id),
            "summary": "terrain labels cannot expose elevation diagnostics",
            "gap_description": "SceneX browse lacks elevation-label overlay required for engineering review",
            "gap_capability": "scenex.terrain.elevation_overlay",
            "owning_repo": "liuxb99/SceneX",
            "verification_plan": [
                "implement typed elevation overlay capability",
                "add permanent REAL browse verification",
                "rerun OpenWorker review bundle",
            ],
            "reviewed_artifacts": [{"logical_name": "result"}],
        },
        allowed_parameter_keys=["camera_height"],
        current_parameters={"camera_height": 10},
    )
    assert result["finding_type"] == "TOOL_GAP"
    assert result["gap_capability"] == "scenex.terrain.elevation_overlay"
    revision = ledger.get_revision(revision_id)
    assert revision["status"] == "rework_required"
    assert revision["gap_owner_repo"] == "liuxb99/SceneX"
    snap = ledger.snapshot(revision["work_id"])
    row = next(r for r in snap["revisions"] if r["revision_id"] == revision_id)
    review = next(c for c in row["checks"] if c["name"] == "LLM Semantic Review")
    assert review["status"] == "failed"
    receipt = next(a for a in row["artifacts"] if a["logical_name"] == "llm-review-receipt.json")
    assert receipt["provenance"]["verdict"] == "FAIL"
    ledger.close()


@pytest.mark.parametrize("missing", ["owning_repo", "gap_capability", "gap_description", "verification_plan"])
def test_tool_gap_fails_closed_when_repair_routing_is_incomplete(tmp_path, missing):
    ledger, cycle, revision_id = _case(tmp_path)
    finding = {
        "verdict": "TOOL_GAP",
        "bundle_manifest_sha256": bundle_manifest_sha256(cycle, revision_id),
        "gap_description": "missing capability",
        "gap_capability": "tool.missing",
        "owning_repo": "liuxb99/tool",
        "verification_plan": ["repair", "rerun"],
    }
    finding.pop(missing)
    with pytest.raises(ReviewGapError):
        apply_review_finding(
            cycle,
            ledger,
            revision_id,
            finding,
            allowed_parameter_keys=["camera_height"],
            current_parameters={"camera_height": 10},
        )
    assert ledger.get_revision(revision_id)["status"] == "verifying"
    ledger.close()


def test_review_finding_rejects_missing_or_stale_manifest_binding(tmp_path):
    ledger, cycle, revision_id = _case(tmp_path)
    base = {
        "verdict": "PASS",
        "summary": "accepted",
        "reviewed_artifacts": [{"logical_name": "result"}],
    }
    with pytest.raises(ReviewGapError, match="requires bundle_manifest_sha256"):
        apply_review_finding(
            cycle,
            ledger,
            revision_id,
            base,
            allowed_parameter_keys=["camera_height"],
            current_parameters={"camera_height": 10},
        )
    stale = dict(base)
    stale["bundle_manifest_sha256"] = "0" * 64
    with pytest.raises(ReviewGapError, match="different bundle manifest"):
        apply_review_finding(
            cycle,
            ledger,
            revision_id,
            stale,
            allowed_parameter_keys=["camera_height"],
            current_parameters={"camera_height": 10},
        )
    assert ledger.get_revision(revision_id)["status"] == "verifying"
    ledger.close()
