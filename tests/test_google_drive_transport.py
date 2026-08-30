from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coworker import google_drive_transport as gdt


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_direct_access_token_has_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN", "token-direct")
    monkeypatch.setenv("OPENWORKER_GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("OPENWORKER_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("OPENWORKER_GOOGLE_REFRESH_TOKEN", "refresh")
    creds = gdt.DriveCredentials.resolve()
    assert creds.access_token == "token-direct"
    assert creds.source == "access_token_env"


def test_authorized_user_file_refreshes_without_secret_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred = tmp_path / "credentials.json"
    cred.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "refresh_token": "refresh-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENWORKER_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("OPENWORKER_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("OPENWORKER_GOOGLE_REFRESH_TOKEN", raising=False)
    monkeypatch.setenv("OPENWORKER_GOOGLE_CREDENTIALS_FILE", str(cred))

    seen: dict[str, object] = {}

    def fake_request(url: str, *, method: str = "GET", headers=None, data=None):
        seen["url"] = url
        seen["method"] = method
        seen["data"] = data
        return {"access_token": "fresh-token"}

    monkeypatch.setattr(gdt, "_json_request", fake_request)
    creds = gdt.DriveCredentials.resolve()
    assert creds.access_token == "fresh-token"
    assert creds.source == "oauth_refresh"
    assert seen["url"] == gdt.TOKEN_ENDPOINT
    assert seen["method"] == "POST"
    assert b"refresh-token" in seen["data"]


def test_write_receipt_strips_known_secret_keys(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    gdt.write_receipt(
        target,
        {
            "schema": "x",
            "access_token": "do-not-write",
            "refresh_token": "do-not-write",
            "client_secret": "do-not-write",
            "Authorization": "Bearer do-not-write",
            "drive_file_id": "abc",
        },
    )
    text = target.read_text(encoding="utf-8")
    assert "do-not-write" not in text
    payload = json.loads(text)
    assert payload["drive_file_id"] == "abc"


def test_deterministic_zip_same_content_same_hash(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "b.txt").write_text("B", encoding="utf-8")
    sub = root / "a"
    sub.mkdir()
    (sub / "a.txt").write_text("A", encoding="utf-8")

    first = gdt.deterministic_zip(root)
    second = gdt.deterministic_zip(root)
    try:
        assert _sha(first) == _sha(second)
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


def test_upload_rejects_remote_size_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"12345")
    transport = gdt.GoogleDriveTransport(gdt.DriveCredentials("token", "test"))

    def fake_request(url: str, *, method: str = "GET", headers=None, data=None):
        return {"id": "drive-id", "name": "artifact.bin", "size": "999"}

    monkeypatch.setattr(gdt, "_json_request", fake_request)
    with pytest.raises(gdt.GoogleDriveTransportError, match="size mismatch"):
        transport.upload_file(source)
