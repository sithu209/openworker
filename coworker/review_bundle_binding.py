"""Portable binding helpers for immutable OpenWorker review bundles."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .review_cycle import ReviewCycleError


def manifest_sha256(bundle_root: str | Path) -> str:
    bundle = Path(bundle_root).expanduser().resolve()
    manifest = bundle / "manifest.json"
    if not manifest.is_file() or manifest.stat().st_size <= 0:
        raise ReviewCycleError(f"review manifest missing/empty: {manifest}")
    digest = hashlib.sha256()
    with manifest.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest_sha256_sidecar(bundle_root: str | Path) -> str:
    bundle = Path(bundle_root).expanduser().resolve()
    digest = manifest_sha256(bundle)
    sidecar = bundle / "manifest.sha256"
    if sidecar.exists():
        existing = sidecar.read_text(encoding="ascii").strip().lower()
        if existing != digest:
            raise ReviewCycleError(
                f"existing manifest.sha256 does not match immutable manifest: expected={digest} actual={existing}"
            )
        return digest
    sidecar.write_text(digest + "\n", encoding="ascii")
    return digest


__all__ = ["manifest_sha256", "write_manifest_sha256_sidecar"]
