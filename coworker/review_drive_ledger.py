"""Bind Google Drive review publication back into the durable WorkLedger."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .review_drive import (
    GoogleDriveAPIClient,
    PUBLISH_RECEIPT_NAME,
    ReviewDriveError,
    ReviewDriveUploader,
    ReviewPublishReceipt,
    publish_review_bundle,
)
from .work_ledger import WorkLedger


def publish_review_bundle_to_ledger(
    ledger: WorkLedger,
    revision_id: str,
    bundle_root: str | Path,
    *,
    work_code: str,
    root_folder_id: str,
    machine_id: str,
    metadata: Mapping[str, Any] | None = None,
    uploader: ReviewDriveUploader | None = None,
) -> ReviewPublishReceipt:
    """Publish a review bundle, then persist the cloud identity as ledger evidence.

    The Drive receipt is recorded only after the final receipt itself has uploaded
    successfully.  If publication raises, no WorkLedger success check is written.
    """
    expected_revision = str(revision_id or "").strip()
    if not expected_revision:
        raise ReviewDriveError("revision id must not be empty")
    revision = ledger.get_revision(expected_revision)
    if revision["status"] not in {"open", "executing", "verifying", "blocked"}:
        raise ReviewDriveError(f"cannot publish immutable revision status={revision['status']}")

    source = Path(bundle_root).expanduser().resolve()
    if source.name != expected_revision:
        raise ReviewDriveError(
            f"review bundle revision mismatch: bundle={source.name!r} ledger={expected_revision!r}"
        )

    owned_client: GoogleDriveAPIClient | None = None
    active_uploader = uploader
    if active_uploader is None:
        owned_client = GoogleDriveAPIClient.from_environment()
        active_uploader = owned_client
    try:
        receipt = publish_review_bundle(
            source,
            work_code=work_code,
            root_folder_id=root_folder_id,
            uploader=active_uploader,
            machine_id=machine_id,
            metadata=metadata,
        )
    finally:
        if owned_client is not None:
            owned_client.close()

    receipt_path = source / PUBLISH_RECEIPT_NAME
    if not receipt_path.is_file() or receipt_path.stat().st_size <= 0:
        raise ReviewDriveError(f"publish receipt missing after Drive publication: {receipt_path}")

    evidence = {
        "transport": "google-drive-api",
        "status": "WAITING_LLM_REVIEW",
        "machine_id": receipt.machine_id,
        "drive_root_folder_id": receipt.drive_root_folder_id,
        "drive_revision_folder_id": receipt.drive_revision_folder_id,
        "drive_revision_web_view_link": receipt.drive_revision_web_view_link,
        "bundle_manifest_sha256": receipt.bundle_manifest_sha256,
        "published_file_count": len(receipt.files),
        "metadata": dict(receipt.metadata),
    }
    ledger.add_file_artifact(
        expected_revision,
        logical_name=PUBLISH_RECEIPT_NAME,
        path=receipt_path,
        provenance=evidence,
        verification_status="passed",
    )
    ledger.set_check(
        expected_revision,
        name="Google Drive Review Publication",
        status="passed",
        required=True,
        evidence=evidence,
        reason="review bundle published with cloud file/folder identities",
    )
    ledger.set_revision_status(
        expected_revision,
        "blocked",
        reason="WAITING_LLM_REVIEW: Google Drive API review bundle published",
    )
    return receipt


__all__ = ["publish_review_bundle_to_ledger"]
