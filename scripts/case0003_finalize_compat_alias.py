"""Publish a backwards-compatible latest alias for the stronger Case 0003 finalizer.

Per-revision evidence remains v3. The canonical controller currently consumes the
v2 latest schema, so this alias is only emitted after verifying the v3 receipt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class CompatError(RuntimeError):
    pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    p.add_argument("--revision-id", required=True)
    a = p.parse_args(argv)
    workspace = Path(a.workspace).expanduser().resolve()
    revision_id = str(a.revision_id).strip()
    root = workspace / "acceptance" / "openworker-final"
    source = root / f"reviewed-delivery-finalize-{revision_id}.json"
    if not source.is_file() or source.stat().st_size <= 0:
        raise CompatError(f"v3 finalizer receipt missing/empty: {source}")
    value = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise CompatError("v3 finalizer receipt must be an object")
    if value.get("schema_version") != "openworker-case0003-reviewed-delivery-finalize/v3":
        raise CompatError("v3 finalizer schema required")
    if value.get("ok") is not True or value.get("status") != "DELIVERED":
        raise CompatError("v3 finalizer is not delivered")
    if str(value.get("revision_id") or "") != revision_id:
        raise CompatError("v3 finalizer revision mismatch")
    if str(value.get("accepted_revision_id") or "") != revision_id or str(value.get("delivered_revision_id") or "") != revision_id:
        raise CompatError("v3 finalizer pointer mismatch")
    reviewed = value.get("reviewed_delivery_bytes") or {}
    if not isinstance(reviewed, dict) or any(len(str(reviewed.get(k) or "")) != 64 for k in ("manifest_sha256", "checksum_manifest_sha256", "website_sha256")):
        raise CompatError("v3 reviewed delivery byte binding incomplete")
    alias = dict(value)
    alias["schema_version"] = "openworker-case0003-reviewed-delivery-finalize/v2"
    alias["semantic_contract_version"] = "openworker-case0003-reviewed-delivery-finalize/v3"
    latest = root / "reviewed-delivery-finalize.json"
    latest.write_text(json.dumps(alias, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(alias, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
