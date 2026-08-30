from __future__ import annotations

from pathlib import Path


def test_drive_review_submit_resumes_existing_waiting_revision_before_opening_new_one():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "case0003_local_drive_review_prepare.ps1").read_text(encoding="utf-8")

    assert "$resumeSeal=$false" in script
    assert "openworker-case0003-drive-review-prepare/v1" in script
    assert "openworker-case0003-drive-review-prepare/v2" in script
    assert "$mode='resume_seal'" in script
    assert "$mode='prepare_and_seal'" in script

    resume_branch = script.split("if($resumeSeal){", 1)[1].split("}else{", 1)[0]
    assert "case0003_seal_drive_review.py" in resume_branch
    assert "case0003_prepare_drive_review.py" not in resume_branch


def test_drive_review_submit_keeps_duplicate_suppression_and_local_only_transport():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "case0003_local_drive_review_prepare.ps1").read_text(encoding="utf-8")

    assert "accepted','queued_local','starting','running" in script
    assert "suppressed_duplicate=$true" in script
    assert "google-drive-desktop-sync+immutable-zip" in script
    assert "github_business_transport=$false" in script
