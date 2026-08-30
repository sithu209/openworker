from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from coworker.drive_ingress import (
    GoogleDriveRawDownloadClient,
    ingress_drive_file_atomic,
    write_ingress_receipt,
)
from coworker.review_drive import ReviewDriveError
from coworker.secrets import SecretStore


class FakeDownloader:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def download_raw_file(self, *, file_id: str, destination: Path) -> int:
        assert file_id == "drive-file-1"
        self.calls += 1
        destination.write_bytes(self.payload)
        return len(self.payload)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_drive_ingress_publishes_then_is_idempotent(tmp_path: Path) -> None:
    payload = b"immutable standards bundle bytes"
    downloader = FakeDownloader(payload)
    destination = tmp_path / "nested" / "bundle.zip"

    first = ingress_drive_file_atomic(
        downloader,
        file_id="drive-file-1",
        destination=destination,
        expected_sha256=_sha(payload),
        expected_size_bytes=len(payload),
        machine_id="DESKTOP-ODAQN0D",
        metadata={"request_id": "req-1"},
    )
    assert first.mode == "published"
    assert destination.read_bytes() == payload
    assert downloader.calls == 1

    second = ingress_drive_file_atomic(
        downloader,
        file_id="drive-file-1",
        destination=destination,
        expected_sha256=_sha(payload),
        expected_size_bytes=len(payload),
        machine_id="DESKTOP-ODAQN0D",
    )
    assert second.mode == "idempotent"
    assert downloader.calls == 1

    receipt_path = write_ingress_receipt(first, tmp_path / "receipt.json")
    text = receipt_path.read_text(encoding="utf-8")
    assert '"schema_version": "openworker-drive-ingress-receipt/v1"' in text
    assert '"status": "PASS"' in text


def test_drive_ingress_rejects_wrong_download_bytes(tmp_path: Path) -> None:
    expected = b"expected immutable bytes"
    downloader = FakeDownloader(b"tampered immutable bytes")
    destination = tmp_path / "bundle.zip"

    with pytest.raises(ReviewDriveError, match="sha256 mismatch"):
        ingress_drive_file_atomic(
            downloader,
            file_id="drive-file-1",
            destination=destination,
            expected_sha256=_sha(expected),
            expected_size_bytes=len(b"tampered immutable bytes"),
            machine_id="DESKTOP-ODAQN0D",
        )
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.tmp.*"))


def test_drive_ingress_rejects_wrong_download_size(tmp_path: Path) -> None:
    payload = b"payload"
    downloader = FakeDownloader(payload)
    destination = tmp_path / "bundle.zip"

    with pytest.raises(ReviewDriveError, match="downloaded size mismatch"):
        ingress_drive_file_atomic(
            downloader,
            file_id="drive-file-1",
            destination=destination,
            expected_sha256=_sha(payload),
            expected_size_bytes=len(payload) + 1,
            machine_id="DESKTOP-ODAQN0D",
        )
    assert not destination.exists()


def test_drive_ingress_refuses_conflicting_destination(tmp_path: Path) -> None:
    expected = b"expected"
    destination = tmp_path / "bundle.zip"
    destination.write_bytes(b"existing-conflict")
    downloader = FakeDownloader(expected)

    with pytest.raises(ReviewDriveError, match="refusing to overwrite"):
        ingress_drive_file_atomic(
            downloader,
            file_id="drive-file-1",
            destination=destination,
            expected_sha256=_sha(expected),
            expected_size_bytes=len(expected),
            machine_id="DESKTOP-ODAQN0D",
        )
    assert destination.read_bytes() == b"existing-conflict"
    assert downloader.calls == 0


def test_drive_ingress_rejects_invalid_identity(tmp_path: Path) -> None:
    downloader = FakeDownloader(b"x")
    with pytest.raises(ReviewDriveError, match="expected sha256"):
        ingress_drive_file_atomic(
            downloader,
            file_id="drive-file-1",
            destination=tmp_path / "bundle.zip",
            expected_sha256="bad",
            expected_size_bytes=1,
        )


def test_drive_client_reuses_machine_local_google_drive_secret_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    SecretStore().put(
        "google_drive:account:test@example.invalid",
        {
            "type": "oauth",
            "account_id": "test@example.invalid",
            "access_token": "local-drive-token",
        },
    )

    client = GoogleDriveRawDownloadClient.from_environment()
    try:
        assert client._token() == "local-drive-token"
    finally:
        client.close()
