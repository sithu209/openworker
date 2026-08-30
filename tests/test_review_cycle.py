from __future__ import annotations

import json

import pytest

from coworker.review_cycle import ReviewArtifact, ReviewCycle, ReviewCycleError
from coworker.work_ledger import WorkLedger


def _fixture(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code="OWJ-REVIEW-1", title="review fixture", workspace=str(workspace))
    revision_id = work["head_revision_id"]
    artifact = workspace / "render.png"
    artifact.write_bytes(b"fake-png-content")
    ledger.set_revision_status(revision_id, "verifying")
    return workspace, ledger, work, revision_id, artifact


def test_review_bundle_is_immutable_and_drive_handoff_is_sha_verified(tmp_path):
    workspace, ledger, work, revision_id, artifact = _fixture(tmp_path)
    cycle = ReviewCycle(workspace)
    bundle = cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("render", artifact)],
        review_dimensions=["composition", "readability"],
        current_parameters={"camera_height": 12.0},
        allowed_parameter_keys=["camera_height"],
        capability_id="scenex.render",
        owning_repo="liuxb99/SceneX",
    )
    request = json.loads((bundle / "review-request.json").read_text(encoding="utf-8"))
    assert request["revision_id"] == revision_id
    assert request["allowed_parameter_keys"] == ["camera_height"]
    assert request["artifacts"][0]["sha256"]

    drive = tmp_path / "drive-sync"
    drive.mkdir()
    target = cycle.handoff_to_drive_sync(bundle, drive_sync_root=drive, work_code=work["code"])
    assert (target / "review-request.json").is_file()
    assert (target / "artifacts" / "render.png").read_bytes() == artifact.read_bytes()

    with pytest.raises(ReviewCycleError, match="already exists"):
        cycle.build_bundle(
            ledger,
            revision_id,
            artifacts=[ReviewArtifact("render", artifact)],
            review_dimensions=["composition"],
            current_parameters={},
            allowed_parameter_keys=[],
            capability_id="scenex.render",
            owning_repo="liuxb99/SceneX",
        )
    ledger.close()


def test_pass_records_required_llm_review_check(tmp_path):
    workspace, ledger, _, revision_id, artifact = _fixture(tmp_path)
    cycle = ReviewCycle(workspace)
    cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("render", artifact)],
        review_dimensions=["quality"],
        current_parameters={"steps": 20},
        allowed_parameter_keys=["steps"],
        capability_id="video.generate",
        owning_repo="liuxb99/ComfyX",
    )
    result = cycle.apply_receipt(
        ledger,
        revision_id,
        {"verdict": "PASS", "summary": "quality accepted", "reviewed_artifacts": [{"logical_name": "render"}]},
        allowed_parameter_keys=["steps"],
        current_parameters={"steps": 20},
    )
    assert result["verdict"] == "PASS"
    snap = ledger.snapshot(ledger.get_revision(revision_id)["work_id"])
    rev = next(r for r in snap["revisions"] if r["revision_id"] == revision_id)
    review = next(c for c in rev["checks"] if c["name"] == "LLM Semantic Review")
    assert review["required"] is True
    assert review["status"] == "passed"
    assert any(a["logical_name"] == "llm-review-receipt.json" for a in rev["artifacts"])
    ledger.close()


def test_tune_creates_child_revision_and_preserves_parameter_delta(tmp_path):
    workspace, ledger, _, revision_id, artifact = _fixture(tmp_path)
    cycle = ReviewCycle(workspace)
    cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("render", artifact)],
        review_dimensions=["framing"],
        current_parameters={"camera_height": 12.0, "fov": 60},
        allowed_parameter_keys=["camera_height", "fov"],
        capability_id="scenex.render",
        owning_repo="liuxb99/SceneX",
    )
    result = cycle.apply_receipt(
        ledger,
        revision_id,
        {
            "verdict": "TUNE",
            "summary": "bridge is too small in frame",
            "parameter_changes": [
                {
                    "parameter": "camera_height",
                    "before": 12.0,
                    "after": 9.0,
                    "reason": "bring camera closer",
                    "expected_effect": "bridge occupies more pixels",
                }
            ],
        },
        allowed_parameter_keys=["camera_height", "fov"],
        current_parameters={"camera_height": 12.0, "fov": 60},
    )
    child = ledger.get_revision(result["next_revision_id"])
    assert child["parent_revision_id"] == revision_id
    assert child["plan"]["revision_role"] == "tuning"
    assert child["plan"]["parameter_delta"][0]["before"] == 12.0
    assert child["plan"]["parameter_delta"][0]["after"] == 9.0
    assert result["parameters"]["camera_height"] == 9.0
    assert ledger.get_revision(revision_id)["status"] == "blocked"
    ledger.close()


def test_tune_rejects_non_allowlisted_parameter_and_wrong_before_value(tmp_path):
    workspace, ledger, _, revision_id, artifact = _fixture(tmp_path)
    cycle = ReviewCycle(workspace)
    cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("render", artifact)],
        review_dimensions=["quality"],
        current_parameters={"steps": 20},
        allowed_parameter_keys=["steps"],
        capability_id="video.generate",
        owning_repo="liuxb99/ComfyX",
    )
    with pytest.raises(ReviewCycleError, match="non-allowlisted"):
        cycle.apply_receipt(
            ledger,
            revision_id,
            {"verdict": "TUNE", "parameter_changes": [{"parameter": "model_path", "before": "a", "after": "b"}]},
            allowed_parameter_keys=["steps"],
            current_parameters={"steps": 20},
        )

    # A rejected receipt is intentionally durable, so use a new revision/bundle for
    # the next independent review attempt rather than overwriting review history.
    child = ledger.open_revision(ledger.get_revision(revision_id)["work_id"], kind="progress", parent_revision_id=revision_id)
    rid2 = child["revision_id"]
    ledger.set_revision_status(rid2, "verifying")
    artifact2 = workspace / "render2.png"
    artifact2.write_bytes(b"second-render")
    cycle.build_bundle(
        ledger,
        rid2,
        artifacts=[ReviewArtifact("render", artifact2)],
        review_dimensions=["quality"],
        current_parameters={"steps": 20},
        allowed_parameter_keys=["steps"],
        capability_id="video.generate",
        owning_repo="liuxb99/ComfyX",
    )
    with pytest.raises(ReviewCycleError, match="before-value mismatch"):
        cycle.apply_receipt(
            ledger,
            rid2,
            {"verdict": "TUNE", "parameter_changes": [{"parameter": "steps", "before": 18, "after": 24}]},
            allowed_parameter_keys=["steps"],
            current_parameters={"steps": 20},
        )
    ledger.close()


def test_fail_moves_revision_to_rework_required_with_owner(tmp_path):
    workspace, ledger, _, revision_id, artifact = _fixture(tmp_path)
    cycle = ReviewCycle(workspace)
    cycle.build_bundle(
        ledger,
        revision_id,
        artifacts=[ReviewArtifact("render", artifact)],
        review_dimensions=["semantic correctness"],
        current_parameters={},
        allowed_parameter_keys=[],
        capability_id="cad.render",
        owning_repo="liuxb99/DWG_todo",
    )
    result = cycle.apply_receipt(
        ledger,
        revision_id,
        {
            "verdict": "FAIL",
            "summary": "beam geometry is structurally wrong",
            "owning_repo": "liuxb99/DWG_todo",
            "verification_plan": ["repair native solid generation", "rerun REAL reopen"],
        },
        allowed_parameter_keys=[],
        current_parameters={},
    )
    assert result["verdict"] == "FAIL"
    failed = ledger.get_revision(revision_id)
    assert failed["status"] == "rework_required"
    assert failed["gap_owner_repo"] == "liuxb99/DWG_todo"
    ledger.close()
