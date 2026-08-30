from __future__ import annotations

from pathlib import Path


def test_case0003_github_drive_business_workflow_is_retired():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "case-0003-drive-api-publish-ul7.yml").read_text(encoding="utf-8")

    assert "[RETIRED]" in workflow
    assert "workflow_dispatch" in workflow
    assert "push:" not in workflow
    assert "CASE0003_DRIVE_API_WORKFLOW_RETIRED" in workflow
    assert "must not publish business artifacts" in workflow
    assert "OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN" not in workflow
    assert "runs-on: [self-hosted, Windows, X64, UL7]" not in workflow


def test_case0003_local_first_drive_review_uses_immutable_zip_and_connector_return_loop():
    root = Path(__file__).resolve().parents[1]
    submit = (root / "scripts" / "case0003_local_drive_review_prepare.ps1").read_text(encoding="utf-8")
    sealer = (root / "scripts" / "case0003_seal_drive_review.py").read_text(encoding="utf-8")
    ingress = (root / "scripts" / "case0003_local_apply_drive_review.ps1").read_text(encoding="utf-8")
    apply_review = (root / "scripts" / "case0003_apply_connector_review.py").read_text(encoding="utf-8")
    finalizer = (root / "scripts" / "case0003_finalize_reviewed_delivery.py").read_text(encoding="utf-8")
    controller = (root / "scripts" / "case0003_local_continue.ps1").read_text(encoding="utf-8")

    assert "case0003_seal_drive_review.py" in submit
    assert "google-drive-desktop-sync+immutable-zip" in submit
    assert "openworker-case0003-drive-review-prepare/v2" in sealer
    assert "review_zip_sha256" in sealer
    assert "drive_sync_zip_target" in sealer
    assert "connector-review-receipt.json" in ingress
    assert "google-drive-desktop-sync->openworker-local-job" in ingress
    assert "drive_revision_folder_id" in apply_review
    assert "drive_zip_file_id" in apply_review
    assert "openworker-case0003-connector-review-apply/v3" in apply_review
    assert "openworker-case0003-reviewed-delivery-finalize/v2" in finalizer
    assert "DriveReceipt-OK" in controller
    assert "case0003_local_apply_drive_review.ps1" in controller
    assert "openworker/case0003-local-continue/v8" in controller
    assert "github_business_transport=$false" in controller
