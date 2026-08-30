from __future__ import annotations

import json

import pytest

from coworker.review_cycle import ReviewArtifact, ReviewCycle
from coworker.review_gap import ReviewGapError, apply_review_finding, bundle_manifest_sha256
from coworker.work_ledger import WorkLedger


def _setup(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code="OWJ-COVERAGE", title="coverage", workspace=str(workspace))
    rid = work["head_revision_id"]
    ledger.set_revision_status(rid, "verifying")
    a = workspace / "a.png"
    b = workspace / "b.html"
    a.write_bytes(b"image-a")
    b.write_text("<html>delivery</html>", encoding="utf-8")
    cycle = ReviewCycle(workspace)
    bundle = cycle.build_bundle(
        ledger,
        rid,
        artifacts=[ReviewArtifact("scene", a), ReviewArtifact("delivery", b)],
        review_dimensions=["visual", "semantic"],
        current_parameters={},
        allowed_parameter_keys=[],
        capability_id="case.final.review",
        owning_repo="liuxb99/openworker",
    )
    request = json.loads((bundle / "review-request.json").read_text(encoding="utf-8"))
    return workspace, ledger, work, rid, cycle, request


def test_pass_rejects_partial_review_bundle(tmp_path):
    _, ledger, _, rid, cycle, _ = _setup(tmp_path)
    with pytest.raises(ReviewGapError, match="complete review bundle"):
        apply_review_finding(
            cycle,
            ledger,
            rid,
            {
                "verdict": "PASS",
                "bundle_manifest_sha256": bundle_manifest_sha256(cycle, rid),
                "summary": "looks good",
                "reviewed_artifacts": [{"logical_name": "scene"}],
            },
            allowed_parameter_keys=[],
            current_parameters={},
        )
    assert ledger.get_revision(rid)["status"] == "verifying"
    ledger.close()


def test_pass_enriches_every_reviewed_artifact_with_authoritative_sha(tmp_path):
    _, ledger, work, rid, cycle, request = _setup(tmp_path)
    result = apply_review_finding(
        cycle,
        ledger,
        rid,
        {
            "verdict": "PASS",
            "bundle_manifest_sha256": bundle_manifest_sha256(cycle, rid),
            "summary": "all review artifacts accepted",
            "reviewed_artifacts": [
                {"logical_name": "delivery"},
                {"logical_name": "scene"},
            ],
        },
        allowed_parameter_keys=[],
        current_parameters={},
    )
    assert result["verdict"] == "PASS"
    snapshot = ledger.snapshot(work["work_id"])
    revision = next(item for item in snapshot["revisions"] if item["revision_id"] == rid)
    review_check = next(item for item in revision["checks"] if item["name"] == "LLM Semantic Review")
    reviewed = review_check["evidence"]["reviewed_artifacts"]
    expected = {item["logical_name"]: item["sha256"] for item in request["artifacts"]}
    assert {item["logical_name"]: item["sha256"] for item in reviewed} == expected
    ledger.close()
