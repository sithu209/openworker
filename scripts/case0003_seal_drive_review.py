"""Seal the prepared Case 0003 review bundle into an immutable Drive-synced ZIP.

This is the local-first replacement for the old GitHub Actions Drive API publication
identity. The ZIP bytes are deterministic for a given bundle, copied into the same
bounded Google Drive Desktop sync parent, and recorded in the review-prepare receipt.
Cloud Drive folder/file IDs are intentionally filled later by the ChatGPT connector.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any


class SealError(RuntimeError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise SealError(f"{label} missing/empty: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SealError(f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _deterministic_zip(source: Path, target: Path) -> None:
    files = sorted(p for p in source.rglob("*") if p.is_file())
    if not files:
        raise SealError("review bundle contains no files")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in files:
                rel = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zf.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        if tmp.stat().st_size <= 0:
            raise SealError("generated review ZIP is empty")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _copy_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".uploading", dir=str(target.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(source, tmp)
        if _sha256(tmp) != _sha256(source):
            raise SealError("Drive sync ZIP copy SHA mismatch")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    args = p.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    acceptance = workspace / "acceptance" / "openworker-final"
    latest = acceptance / "drive-review-prepare.json"
    receipt = _load(latest, "Drive review prepare receipt")
    if receipt.get("schema_version") not in {"openworker-case0003-drive-review-prepare/v1", "openworker-case0003-drive-review-prepare/v2"}:
        raise SealError("unsupported Drive review prepare schema")
    if str(receipt.get("status") or "") != "WAITING_DRIVE_REVIEW":
        raise SealError("Drive review is not waiting for connector review")
    revision_id = str(receipt.get("revision_id") or "").strip()
    if not revision_id:
        raise SealError("revision_id missing")
    bundle = Path(str(receipt.get("bundle_root") or "")).expanduser().resolve()
    drive_target = Path(str(receipt.get("drive_sync_target") or "")).expanduser().resolve()
    if not bundle.is_dir() or not drive_target.is_dir():
        raise SealError("local or Drive-synced review folder is unavailable")
    manifest = bundle / "manifest.json"
    expected_manifest = str(receipt.get("bundle_manifest_sha256") or "").strip().lower()
    if _sha256(manifest) != expected_manifest:
        raise SealError("review bundle manifest changed after prepare")

    zip_path = bundle.parent / f"{revision_id}.zip"
    _deterministic_zip(bundle, zip_path)
    zip_sha = _sha256(zip_path)
    drive_zip = drive_target.parent / f"{revision_id}.zip"
    _copy_atomic(zip_path, drive_zip)
    if _sha256(drive_zip) != zip_sha:
        raise SealError("Drive-synced ZIP SHA mismatch")

    receipt.update(
        {
            "schema_version": "openworker-case0003-drive-review-prepare/v2",
            "review_zip_path": str(zip_path),
            "review_zip_sha256": zip_sha,
            "drive_sync_zip_target": str(drive_zip),
            "cloud_identity_required": ["drive_revision_folder_id", "drive_zip_file_id"],
            "transport": "google-drive-desktop-sync+connector-observed-cloud-identity",
        }
    )
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, default=str)
    latest.write_text(payload, encoding="utf-8")
    (acceptance / f"drive-review-prepare-{revision_id}.json").write_text(payload, encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0003_DRIVE_REVIEW_SEAL_FAIL {exc}")
        raise
