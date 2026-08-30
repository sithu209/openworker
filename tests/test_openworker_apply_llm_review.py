from __future__ import annotations

import hashlib
import json

from coworker.review_cycle import ReviewArtifact, ReviewCycle
from coworker.work_ledger import WorkLedger
from scripts import openworker_apply_llm_review


def _fixture(tmp_path, *, parameters=None, allowed=None):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code="OWJ-GENERIC-REVIEW", title="generic review", workspace=str(workspace))
    rid = work["head_revision_id"]
    artifact = workspace / "result.png"
    artifact.write_bytes(b"physical-result")
    ledger.set_revision_status(rid, "verifying")
    cycle = ReviewCycle(workspace)
    bundle = cycle.build_bundle(
        ledger,
        rid,
        artifacts=[ReviewArtifact("result", artifact)],
        review_dimensions=["quality"],
        current_parameters=parameters or {},
        allowed_parameter_keys=allowed or [],
        capability_id="generic.review",
        owning_repo="liuxb99/openworker",
    )
    manifest_sha = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    ledger.set_check(rid, name="LLM Semantic Review", status="pending", required=True)
    ledger.set_revision_status(rid, "blocked", reason="WAITING_LLM_REVIEW")
    ledger.close()
    return workspace, rid, manifest_sha


def test_generic_pass_accepts_without_implicit_delivery(tmp_path):
    workspace, rid, manifest_sha = _fixture(tmp_path)
    receipt = workspace / "pass.json"
    receipt.write_text(
        json.dumps(
            {
                "verdict": "PASS",
                "bundle_manifest_sha256": manifest_sha,
                "summary": "accepted",
                "reviewed_artifacts": [{"logical_name": "result"}],
            }
        ),
        encoding="utf-8",
    )
    assert openworker_apply_llm_review.main(
        [
            "--workspace", str(workspace),
            "--work-code", "OWJ-GENERIC-REVIEW",
            "--revision-id", rid,
            "--receipt", str(receipt),
        ]
    ) == 0
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code("OWJ-GENERIC-REVIEW")
        assert work["accepted_revision_id"] == rid
        assert not work["delivered_revision_id"]
        assert ledger.get_revision(rid)["status"] == "accepted"
    finally:
        ledger.close()


def test_generic_tune_creates_native_tuning_revision(tmp_path):
    workspace, rid, manifest_sha = _fixture(
        tmp_path,
        parameters={"camera_height": 12},
        allowed=["camera_height"],
    )
    receipt = workspace / "tune.json"
    receipt.write_text(
        json.dumps(
            {
                "verdict": "TUNE",
                "bundle_manifest_sha256": manifest_sha,
                "summary": "move camera closer",
                "parameter_changes": [
                    {
                        "parameter": "camera_height",
                        "before": 12,
                        "after": 9,
                        "reason": "subject too small",
                        "expected_effect": "subject occupies more pixels",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert openworker_apply_llm_review.main(
        [
            "--workspace", str(workspace),
            "--work-code", "OWJ-GENERIC-REVIEW",
            "--revision-id", rid,
            "--receipt", str(receipt),
        ]
    ) == 4
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code("OWJ-GENERIC-REVIEW")
        head = ledger.get_revision(work["head_revision_id"])
        assert head["kind"] == "tuning"
        assert head["parent_revision_id"] == rid
        assert head["plan"]["parameters"]["camera_height"] == 9
        assert not work["accepted_revision_id"]
        assert not work["delivered_revision_id"]
    finally:
        ledger.close()
