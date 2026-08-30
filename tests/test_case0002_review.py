from __future__ import annotations

import hashlib
import json

from coworker.work_ledger import WorkLedger
from scripts import case0002_apply_llm_review, case0002_review_handoff


def _workspace(tmp_path):
    workspace = tmp_path / "0002"
    (workspace / "presentation").mkdir(parents=True)
    (workspace / "visual-assets" / "shots" / "shot-1").mkdir(parents=True)
    (workspace / "evidence").mkdir(parents=True)
    (workspace / "presentation" / "storyboard-request.bound.json").write_text("{}", encoding="utf-8")
    (workspace / "presentation" / "storyboard.pptx").write_bytes(b"PK-fake-pptx-for-review-governance")
    (workspace / "presentation" / "storyboard.manifest.json").write_text("{}", encoding="utf-8")
    (workspace / "visual-assets" / "shots" / "shot-1" / "storyboard.png").write_bytes(b"fake-image")
    (workspace / "evidence" / "storyboard-image-real.json").write_text('{"status":"succeeded"}', encoding="utf-8")
    return workspace


def test_case0002_storyboard_handoff_blocks_acceptance_until_llm_receipt(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    drive = tmp_path / "drive"
    drive.mkdir()
    monkeypatch.setenv("COMPUTERNAME", case0002_review_handoff.ASSIGNED_HOST)

    assert case0002_review_handoff.main([
        "--workspace", str(workspace),
        "--phase", "storyboard",
        "--drive-sync-root", str(drive),
    ]) == 0

    handoff = json.loads((workspace / "acceptance" / "openworker-review" / "handoff-latest.json").read_text(encoding="utf-8"))
    assert handoff["status"] == "WAITING_LLM_REVIEW"
    assert handoff["accepted_revision_id"] == ""
    assert handoff["delivered_revision_id"] == ""
    revision_id = handoff["revision_id"]
    assert (drive / case0002_review_handoff.WORK_CODE / revision_id / "review-request.json").is_file()

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(case0002_review_handoff.WORK_CODE)
        assert not work["accepted_revision_id"]
        assert not work["delivered_revision_id"]
        assert ledger.get_revision(revision_id)["status"] == "blocked"
    finally:
        ledger.close()


def test_case0002_pass_receipt_can_accept_and_deliver(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    drive = tmp_path / "drive"
    drive.mkdir()
    monkeypatch.setenv("COMPUTERNAME", case0002_review_handoff.ASSIGNED_HOST)
    assert case0002_review_handoff.main([
        "--workspace", str(workspace),
        "--drive-sync-root", str(drive),
    ]) == 0
    handoff = json.loads((workspace / "acceptance" / "openworker-review" / "handoff-latest.json").read_text(encoding="utf-8"))
    revision_id = handoff["revision_id"]
    review_root = workspace / ".openworker" / "reviews" / revision_id
    review_request = json.loads((review_root / "review-request.json").read_text(encoding="utf-8"))
    reviewed_artifacts = [
        {"logical_name": item["logical_name"]}
        for item in review_request["artifacts"]
    ]
    manifest_sha = hashlib.sha256((review_root / "manifest.json").read_bytes()).hexdigest()
    receipt = workspace / "chatgpt-review.json"
    receipt.write_text(json.dumps({
        "verdict": "PASS",
        "bundle_manifest_sha256": manifest_sha,
        "summary": "storyboard artifacts are coherent and ready for video",
        "reviewed_artifacts": reviewed_artifacts,
    }), encoding="utf-8")

    assert case0002_apply_llm_review.main([
        "--workspace", str(workspace),
        "--revision-id", revision_id,
        "--receipt", str(receipt),
    ]) == 0

    applied = json.loads((workspace / "acceptance" / "openworker-review" / f"llm-review-apply-{revision_id}.json").read_text(encoding="utf-8"))
    assert applied["status"] == "DELIVERED"
    assert applied["accepted_revision_id"] == revision_id
    assert applied["delivered_revision_id"] == revision_id


def test_case0002_final_phase_requires_physical_mp4(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    drive = tmp_path / "drive"
    drive.mkdir()
    monkeypatch.setenv("COMPUTERNAME", case0002_review_handoff.ASSIGNED_HOST)
    try:
        case0002_review_handoff.main([
            "--workspace", str(workspace),
            "--phase", "final",
            "--drive-sync-root", str(drive),
        ])
    except Exception as exc:
        assert "requires at least one physical MP4" in str(exc)
    else:
        raise AssertionError("final review must fail closed without a physical MP4")
