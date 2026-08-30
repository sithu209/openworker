from __future__ import annotations

import json
from pathlib import Path

from coworker.review_drive_ledger import publish_review_bundle_to_ledger
from coworker.work_ledger import WorkLedger


class FakeUploader:
    def __init__(self) -> None:
        self.counter = 0

    def _identity(self, kind: str):
        self.counter += 1
        item_id = f"{kind}-{self.counter}"
        return {"id": item_id, "webViewLink": f"https://drive.example/{item_id}"}

    def ensure_folder(self, *, name: str, parent_id: str, app_properties):
        return self._identity("folder")

    def upload_file(self, *, path: Path, name: str, parent_id: str, sha256: str, mime_type: str, app_properties):
        item = self._identity("file")
        item["size"] = str(Path(path).stat().st_size)
        item["appProperties"] = {**dict(app_properties), "openworkerSha256": sha256}
        return item


def test_drive_publish_receipt_is_durable_workledger_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.create_work(code="OWJ-CLOUD-1", title="cloud review", workspace=str(workspace))
    revision_id = work["head_revision_id"]
    ledger.set_revision_status(revision_id, "verifying")

    bundle = workspace / ".openworker" / "reviews" / revision_id
    (bundle / "artifacts").mkdir(parents=True)
    (bundle / "artifacts" / "result.png").write_bytes(b"result")
    (bundle / "review-request.json").write_text(
        json.dumps({"revision_id": revision_id}), encoding="utf-8"
    )
    (bundle / "manifest.json").write_text(
        json.dumps({"schema_version": "openworker-review-bundle/v1", "revision_id": revision_id}),
        encoding="utf-8",
    )

    receipt = publish_review_bundle_to_ledger(
        ledger,
        revision_id,
        bundle,
        work_code=work["code"],
        root_folder_id="drive-root",
        machine_id="DESKTOP-UL7V2VV",
        metadata={"case_id": "0003", "job_id": "job-1"},
        uploader=FakeUploader(),
    )

    assert receipt.drive_revision_folder_id
    assert ledger.get_revision(revision_id)["status"] == "blocked"
    snapshot = ledger.snapshot(work["work_id"])
    revision = next(item for item in snapshot["revisions"] if item["revision_id"] == revision_id)
    artifact = next(item for item in revision["artifacts"] if item["logical_name"] == "review-publish-receipt.json")
    assert artifact["verification_status"] == "passed"
    assert artifact["provenance"]["transport"] == "google-drive-api"
    assert artifact["provenance"]["drive_revision_folder_id"] == receipt.drive_revision_folder_id
    check = next(item for item in revision["checks"] if item["name"] == "Google Drive Review Publication")
    assert check["required"] is True
    assert check["status"] == "passed"
    assert check["evidence"]["status"] == "WAITING_LLM_REVIEW"
    assert "WAITING_LLM_REVIEW" in ledger.get_revision(revision_id)["reason"]
    ledger.close()
