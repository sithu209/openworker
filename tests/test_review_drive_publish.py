from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker.review_drive import (
    GoogleDriveAPIClient,
    PUBLISH_RECEIPT_NAME,
    ReviewDriveError,
    publish_review_bundle,
)


class FakeUploader:
    def __init__(self) -> None:
        self.folders: list[dict] = []
        self.uploads: list[dict] = []

    def ensure_folder(self, *, name: str, parent_id: str, app_properties):
        item_id = f"folder-{len(self.folders) + 1}"
        record = {
            "name": name,
            "parent_id": parent_id,
            "app_properties": dict(app_properties),
            "id": item_id,
            "webViewLink": f"https://drive.example/folders/{item_id}",
        }
        self.folders.append(record)
        return record

    def upload_file(self, *, path: Path, name: str, parent_id: str, sha256: str, mime_type: str, app_properties):
        item_id = f"file-{len(self.uploads) + 1}"
        record = {
            "path": Path(path),
            "name": name,
            "parent_id": parent_id,
            "sha256": sha256,
            "mime_type": mime_type,
            "app_properties": dict(app_properties),
            "id": item_id,
            "webViewLink": f"https://drive.example/files/{item_id}",
            "size": str(Path(path).stat().st_size),
        }
        self.uploads.append(record)
        return record


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "REV-0007"
    (bundle / "artifacts").mkdir(parents=True)
    (bundle / "artifacts" / "render.png").write_bytes(b"render-v7")
    (bundle / "review-request.json").write_text('{"revision_id":"REV-0007"}', encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps({"schema_version": "openworker-review-bundle/v1", "revision_id": "REV-0007"}),
        encoding="utf-8",
    )
    return bundle


def test_publish_review_bundle_returns_cloud_identity_and_final_receipt(tmp_path):
    bundle = _bundle(tmp_path)
    uploader = FakeUploader()

    receipt = publish_review_bundle(
        bundle,
        work_code="OWJ-0004",
        root_folder_id="drive-root-123",
        uploader=uploader,
        machine_id="DESKTOP-O87",
        metadata={"case_id": "0004", "job_id": "job-77", "run_id": "run-88"},
    )

    payload = receipt.to_dict()
    assert payload["schema_version"] == "openworker-review-publish-receipt/v1"
    assert payload["transport"] == "google-drive-api"
    assert payload["status"] == "WAITING_LLM_REVIEW"
    assert payload["machine_id"] == "DESKTOP-O87"
    assert payload["drive_root_folder_id"] == "drive-root-123"
    assert payload["drive_revision_folder_id"]
    assert payload["drive_revision_web_view_link"]
    assert payload["bundle_manifest_sha256"]
    assert payload["metadata"]["case_id"] == "0004"
    assert {item["relative_path"] for item in payload["files"]} == {
        "artifacts/render.png",
        "manifest.json",
        "review-request.json",
    }
    assert all(item["drive_file_id"] and item["web_view_link"] for item in payload["files"])

    local_receipt = json.loads((bundle / PUBLISH_RECEIPT_NAME).read_text(encoding="utf-8"))
    assert local_receipt == payload
    assert uploader.uploads[-1]["name"] == PUBLISH_RECEIPT_NAME
    assert PUBLISH_RECEIPT_NAME not in {item["relative_path"] for item in payload["files"]}
    assert any(folder["name"] == "artifacts" for folder in uploader.folders)


def test_publish_requires_machine_identity_and_manifest(tmp_path):
    bundle = _bundle(tmp_path)
    with pytest.raises(ReviewDriveError, match="machine id"):
        publish_review_bundle(
            bundle,
            work_code="OWJ-1",
            root_folder_id="root",
            uploader=FakeUploader(),
            machine_id="",
        )

    (bundle / "manifest.json").unlink()
    with pytest.raises(ReviewDriveError, match="manifest missing"):
        publish_review_bundle(
            bundle,
            work_code="OWJ-1",
            root_folder_id="root",
            uploader=FakeUploader(),
            machine_id="DESKTOP-1",
        )


def test_api_client_fails_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)

    import google.auth

    def fail_default(*args, **kwargs):
        raise RuntimeError("no adc")

    monkeypatch.setattr(google.auth, "default", fail_default)
    with pytest.raises(ReviewDriveError, match="credentials unavailable"):
        GoogleDriveAPIClient.from_environment()
