from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coworker.work_ledger import WorkLedger
from scripts import case0003_finalize_reviewed_delivery as finalize


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code=finalize.JOB_CODE, title="Case 0003")
    revision_id = work["head_revision_id"]
    ledger.set_check(revision_id, name="LLM Semantic Review", status="passed", required=True)
    ledger.accept_revision(revision_id)
    ledger.close()

    delivery_root = workspace / "os-delivery"
    delivery_root.mkdir()
    delivery_manifest = delivery_root / "delivery-manifest.json"
    checksum_manifest = delivery_root / "checksum-manifest.json"
    website = delivery_root / "website" / "index.html"
    website.parent.mkdir()
    delivery_manifest.write_text(json.dumps({
        "schema_version": "delivery-manifest/1.0",
        "delivery_id": "del_current",
        "job_id": "job_current",
        "project_id": "prj_current",
        "revision": 7,
    }), encoding="utf-8")
    checksum_manifest.write_text(json.dumps({"schema_version": "checksum-manifest/1.0", "items": []}), encoding="utf-8")
    website.write_text("<!doctype html><html><body>Case 0003</body></html>", encoding="utf-8")

    bundle_dir = workspace / ".openworker" / "reviews" / revision_id
    bundle_dir.mkdir(parents=True)
    bundle_manifest = bundle_dir / "manifest.json"
    bundle_manifest.write_text(json.dumps({
        "schema_version": "openworker-review-bundle/v1",
        "revision_id": revision_id,
        "files": [
            {"logical_name": "delivery-manifest", "sha256": _sha(delivery_manifest), "size_bytes": delivery_manifest.stat().st_size},
            {"logical_name": "checksum-manifest", "sha256": _sha(checksum_manifest), "size_bytes": checksum_manifest.stat().st_size},
            {"logical_name": "delivery-index", "sha256": _sha(website), "size_bytes": website.stat().st_size},
        ],
    }), encoding="utf-8")
    bundle_sha = _sha(bundle_manifest)

    review_zip = bundle_dir.parent / f"{revision_id}.zip"
    review_zip.write_bytes(b"deterministic-review-zip-fixture")
    review_zip_sha = _sha(review_zip)

    acceptance = workspace / "acceptance" / "openworker-final"
    acceptance.mkdir(parents=True)
    prepare = acceptance / f"drive-review-prepare-{revision_id}.json"
    prepare.write_text(json.dumps({
        "schema_version": "openworker-case0003-drive-review-prepare/v2",
        "case_id": "0003",
        "revision_id": revision_id,
        "status": "WAITING_DRIVE_REVIEW",
        "review_zip_path": str(review_zip),
        "review_zip_sha256": review_zip_sha,
        "bundle_manifest_sha256": bundle_sha,
    }), encoding="utf-8")

    review_apply = acceptance / f"connector-review-apply-{revision_id}.json"
    cloud = {
        "drive_revision_folder_id": "drive-folder",
        "drive_zip_file_id": "drive-zip-file",
        "review_zip_sha256": review_zip_sha,
        "bundle_manifest_sha256": bundle_sha,
    }
    review_apply.write_text(json.dumps({
        "schema_version": "openworker-case0003-connector-review-apply/v3",
        "case_id": "0003",
        "revision_id": revision_id,
        "verdict": "PASS",
        "status": "ACCEPTED_PENDING_FINALIZE",
        "accepted_revision_id": revision_id,
        "delivered_revision_id": "",
        "bundle_manifest_sha256": bundle_sha,
        "review_zip_sha256": review_zip_sha,
        "cloud_publication": cloud,
    }), encoding="utf-8")

    os_receipt = workspace / "evidence" / "case0003-os-delivery-receipt.json"
    os_receipt.parent.mkdir()
    os_receipt.write_text(json.dumps({
        "ok": True,
        "schema_version": "engineering-os-local-delivery-receipt/v1",
        "job_id": "job_current",
        "project_id": "prj_current",
        "delivery_id": "del_current",
        "revision": 7,
        "status": "published",
        "manifest_path": str(delivery_manifest),
        "manifest_sha256": _sha(delivery_manifest),
        "checksum_manifest": str(checksum_manifest),
        "checksum_manifest_sha256": _sha(checksum_manifest),
        "website_entry": str(website),
    }), encoding="utf-8")
    return workspace, revision_id, bundle_manifest, website


def test_finalize_binds_accepted_review_to_exact_current_os_and_drive_bytes(tmp_path: Path):
    workspace, revision_id, _, _ = _fixture(tmp_path)
    assert finalize.main(["--workspace", str(workspace), "--revision-id", revision_id]) == 0
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(finalize.JOB_CODE)
        assert work["accepted_revision_id"] == revision_id
        assert work["delivered_revision_id"] == revision_id
        assert work["status"] == "delivered"
        events = ledger.snapshot(work["work_id"])["revisions"][0]["events"]
        delivered = [x for x in events if x["event_type"] == "revision.delivered"]
        assert len(delivered) == 1
        payload = delivered[0]["payload"]
        assert payload["engineering_os"]["delivery_id"] == "del_current"
        assert payload["engineering_os"]["delivery_revision"] == 7
        assert payload["google_drive"]["drive_zip_file_id"] == "drive-zip-file"
        result = json.loads((workspace / "acceptance" / "openworker-final" / f"reviewed-delivery-finalize-{revision_id}.json").read_text(encoding="utf-8"))
        assert result["schema_version"] == "openworker-case0003-reviewed-delivery-finalize/v3"
        assert result["reviewed_delivery_bytes"]["website_sha256"] == result["engineering_os"]["website_sha256"]
    finally:
        ledger.close()


def test_finalize_rejects_stale_review_bundle_without_moving_delivery_pointer(tmp_path: Path):
    workspace, revision_id, bundle_manifest, _ = _fixture(tmp_path)
    bundle_manifest.write_text("stale bundle bytes", encoding="utf-8")
    with pytest.raises(finalize.FinalizeError, match="review bundle manifest SHA mismatch"):
        finalize.main(["--workspace", str(workspace), "--revision-id", revision_id])
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(finalize.JOB_CODE)
        assert work["accepted_revision_id"] == revision_id
        assert not work["delivered_revision_id"]
    finally:
        ledger.close()


def test_finalize_rejects_os_delivery_bytes_changed_after_chatgpt_review(tmp_path: Path):
    workspace, revision_id, _, website = _fixture(tmp_path)
    website.write_text("<!doctype html><html><body>NEW UNREVIEWED DELIVERY</body></html>", encoding="utf-8")
    with pytest.raises(finalize.FinalizeError, match="website differs from the website reviewed by ChatGPT"):
        finalize.main(["--workspace", str(workspace), "--revision-id", revision_id])
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(finalize.JOB_CODE)
        assert work["accepted_revision_id"] == revision_id
        assert not work["delivered_revision_id"]
        assert work["status"] == "accepted"
    finally:
        ledger.close()
