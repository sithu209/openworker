"""Fail-closed Google Drive raw-file ingress for fixed-machine OpenWorker jobs."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from .review_drive import DRIVE_API_BASE, GoogleDriveAPIClient, ReviewDriveError
from .secrets import SecretStore

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DriveRawDownloader(Protocol):
    def download_raw_file(self, *, file_id: str, destination: Path) -> int: ...


class GoogleDriveRawDownloadClient(GoogleDriveAPIClient):
    """GoogleDriveAPIClient extension for authenticated Drive ``alt=media`` reads."""

    @classmethod
    def from_environment(cls) -> "GoogleDriveRawDownloadClient":
        """Resolve Drive auth without making GitHub Actions secrets authoritative.

        Priority is an explicit process token, then the machine-local OpenWorker
        SecretStore connector profiles, and finally google-auth ADC. Secret values
        are never emitted to logs or receipts.
        """
        token = str(os.environ.get("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN") or "").strip()
        if token:
            return cls(access_token=token)

        store = SecretStore()
        profiles = sorted(
            row["profile"]
            for row in store.status()
            if str(row.get("profile") or "") == "google_drive"
            or str(row.get("profile") or "").startswith("google_drive:")
        )
        for profile in profiles:
            creds = store.get(profile)
            if not isinstance(creds, Mapping):
                continue
            candidate = str(creds.get("access_token") or "").strip()
            if candidate and not (candidate.startswith("${") and candidate.endswith("}")):
                return cls(access_token=candidate)

        return super().from_environment()

    def download_raw_file(self, *, file_id: str, destination: Path) -> int:
        drive_file_id = _required_text(file_id, "Google Drive file id")
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream(
                "GET",
                f"{DRIVE_API_BASE}/files/{drive_file_id}",
                params={"alt": "media", "supportsAllDrives": "true"},
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    detail = response.read().decode("utf-8", errors="replace")[:1000].replace("\n", " ")
                    raise ReviewDriveError(
                        f"Google Drive raw download failed HTTP {response.status_code}: {detail}"
                    )
                total = 0
                with target.open("xb") as fh:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        total += len(chunk)
                    fh.flush()
                    os.fsync(fh.fileno())
        except FileExistsError as exc:
            raise ReviewDriveError(f"download temp destination already exists: {target}") from exc
        except ReviewDriveError:
            raise
        except Exception as exc:
            raise ReviewDriveError(f"Google Drive raw download failed: {exc}") from exc
        return total


@dataclass(frozen=True)
class DriveIngressReceipt:
    drive_file_id: str
    destination: str
    sha256: str
    size_bytes: int
    machine_id: str
    mode: str
    completed_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "openworker-drive-ingress-receipt/v1",
            "transport": "google-drive-api",
            "status": "PASS",
            "drive_file_id": self.drive_file_id,
            "destination": self.destination,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "machine_id": self.machine_id,
            "mode": self.mode,
            "completed_at": self.completed_at,
            "metadata": dict(self.metadata),
        }


def ingress_drive_file_atomic(
    downloader: DriveRawDownloader,
    *,
    file_id: str,
    destination: str | Path,
    expected_sha256: str,
    expected_size_bytes: int,
    machine_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DriveIngressReceipt:
    """Download one immutable Drive file and publish it without overwriting conflicts."""
    drive_file_id = _required_text(file_id, "Google Drive file id")
    digest = str(expected_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise ReviewDriveError("expected sha256 must be exactly 64 lowercase hexadecimal characters")
    expected_size = int(expected_size_bytes)
    if expected_size <= 0:
        raise ReviewDriveError("expected size must be positive")
    machine = _required_text(machine_id or platform.node(), "machine id")
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        if not target.is_file():
            raise ReviewDriveError(f"Drive ingress destination is not a file: {target}")
        actual_size = target.stat().st_size
        actual_sha = _sha256(target)
        if actual_size != expected_size or actual_sha != digest:
            raise ReviewDriveError(
                "refusing to overwrite immutable Drive ingress destination: "
                f"actual_sha256={actual_sha} expected_sha256={digest} "
                f"actual_size={actual_size} expected_size={expected_size} destination={target}"
            )
        return _receipt(
            file_id=drive_file_id,
            destination=target,
            digest=digest,
            size=expected_size,
            machine=machine,
            mode="idempotent",
            metadata=metadata,
        )

    temp = target.with_name(f".{target.name}.tmp.{uuid.uuid4().hex}")
    try:
        downloaded = downloader.download_raw_file(file_id=drive_file_id, destination=temp)
        if downloaded != expected_size:
            raise ReviewDriveError(
                f"Drive ingress downloaded size mismatch: actual={downloaded} expected={expected_size}"
            )
        stat_size = temp.stat().st_size
        if stat_size != expected_size:
            raise ReviewDriveError(
                f"Drive ingress temp size mismatch: actual={stat_size} expected={expected_size}"
            )
        actual_sha = _sha256(temp)
        if actual_sha != digest:
            raise ReviewDriveError(
                f"Drive ingress sha256 mismatch: actual={actual_sha} expected={digest}"
            )
        try:
            os.link(temp, target)
        except FileExistsError as exc:
            raise ReviewDriveError(f"Drive ingress destination appeared during publish: {target}") from exc
        except OSError as exc:
            raise ReviewDriveError(f"Drive ingress atomic publish failed: {exc}") from exc
        temp.unlink()
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)

    final_size = target.stat().st_size
    final_sha = _sha256(target)
    if final_size != expected_size or final_sha != digest:
        raise ReviewDriveError(
            f"Drive ingress final identity mismatch: sha256={final_sha} size={final_size}"
        )
    return _receipt(
        file_id=drive_file_id,
        destination=target,
        digest=digest,
        size=expected_size,
        machine=machine,
        mode="published",
        metadata=metadata,
    )


def write_ingress_receipt(receipt: DriveIngressReceipt, path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp.{uuid.uuid4().hex}")
    payload = json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, target)
    return target


def _receipt(
    *,
    file_id: str,
    destination: Path,
    digest: str,
    size: int,
    machine: str,
    mode: str,
    metadata: Mapping[str, Any] | None,
) -> DriveIngressReceipt:
    return DriveIngressReceipt(
        drive_file_id=file_id,
        destination=str(destination),
        sha256=digest,
        size_bytes=size,
        machine_id=machine,
        mode=mode,
        completed_at=datetime.now(timezone.utc).isoformat(),
        metadata=dict(metadata or {}),
    )


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ReviewDriveError(f"{label} must not be empty")
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DriveIngressReceipt",
    "DriveRawDownloader",
    "GoogleDriveRawDownloadClient",
    "ingress_drive_file_atomic",
    "write_ingress_receipt",
]
