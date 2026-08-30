from __future__ import annotations

import hashlib

import pytest

from coworker.review_bundle_binding import manifest_sha256, write_manifest_sha256_sidecar
from coworker.review_cycle import ReviewCycleError


def test_manifest_sha_sidecar_matches_exact_manifest_bytes(tmp_path):
    bundle = tmp_path / "rev-1"
    bundle.mkdir()
    manifest = bundle / "manifest.json"
    manifest.write_bytes(b'{"revision_id":"rev-1","files":[]}\n')

    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert manifest_sha256(bundle) == expected
    assert write_manifest_sha256_sidecar(bundle) == expected
    assert (bundle / "manifest.sha256").read_text(encoding="ascii") == expected + "\n"

    # Idempotent read of the same immutable binding is allowed.
    assert write_manifest_sha256_sidecar(bundle) == expected


def test_manifest_sha_sidecar_fails_closed_if_existing_binding_is_stale(tmp_path):
    bundle = tmp_path / "rev-2"
    bundle.mkdir()
    (bundle / "manifest.json").write_bytes(b'{"revision_id":"rev-2"}\n')
    (bundle / "manifest.sha256").write_text("0" * 64 + "\n", encoding="ascii")

    with pytest.raises(ReviewCycleError, match="does not match immutable manifest"):
        write_manifest_sha256_sidecar(bundle)
