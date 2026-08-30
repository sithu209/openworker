from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.engineering.engineering_os import EngineeringOSClient, EngineeringOSConfig
from scripts.engineering_source_ingress_action import start_isolated_os


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"{name} is required")
    return text


def bounded(path: Path, root: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"{label} escapes governed workspace: {resolved}") from exc
    return resolved


def load_request(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise RuntimeError("delivery validation request root must be an object")
    return raw


def load_review_provenance(request: dict[str, Any], workspace: Path) -> dict[str, Any]:
    review_path = bounded(Path(required_text(request.get("review_receipt"), "review_receipt")), workspace, "review receipt")
    if not review_path.is_file() or review_path.stat().st_size <= 0:
        raise RuntimeError(f"review receipt missing/empty: {review_path}")
    try:
        receipt = json.loads(review_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("review receipt is not readable JSON") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError("review receipt root must be an object")
    if receipt.get("schema_version") != "openworker-case0005-drive-gate-receipt/v1":
        raise RuntimeError("review receipt schema mismatch")
    if str(receipt.get("case_id") or "") != "0005" or str(receipt.get("step_id") or "") != "0005-100":
        raise RuntimeError("review receipt Case/step identity mismatch")
    if str(receipt.get("decision") or "").upper() != "PASS":
        raise RuntimeError("review receipt decision is not PASS")
    expected = required_text(request.get("expected_accepted_revision_id"), "expected_accepted_revision_id")
    reviewed_revision = required_text(receipt.get("workledger_revision_id"), "review receipt workledger_revision_id")
    accepted_revision = required_text(receipt.get("accepted_revision_id"), "review receipt accepted_revision_id")
    if reviewed_revision != expected or accepted_revision != expected:
        raise RuntimeError(
            f"review receipt accepted revision mismatch: expected={expected} reviewed={reviewed_revision} accepted={accepted_revision}"
        )
    reviewed_files = receipt.get("reviewed_files")
    if not isinstance(reviewed_files, list) or not reviewed_files:
        raise RuntimeError("review receipt contains no reviewed_files")
    for index, item in enumerate(reviewed_files):
        if not isinstance(item, dict):
            raise RuntimeError(f"reviewed_files[{index}] must be an object")
        digest = required_text(item.get("sha256"), f"reviewed_files[{index}].sha256").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError(f"reviewed_files[{index}] SHA256 is invalid")
        required_text(item.get("relative_path"), f"reviewed_files[{index}].relative_path")
        required_text(item.get("drive_file_id"), f"reviewed_files[{index}].drive_file_id")
    return {
        "review_receipt": str(review_path),
        "review_receipt_sha256": sha256_file(review_path),
        "decision": "PASS",
        "reviewer": required_text(receipt.get("reviewer"), "reviewer"),
        "accepted_revision_id": accepted_revision,
        "drive_revision_folder_id": required_text(receipt.get("drive_revision_folder_id"), "drive_revision_folder_id"),
        "bundle_manifest_sha256": required_text(receipt.get("bundle_manifest_sha256"), "bundle_manifest_sha256").lower(),
        "reviewed_files": reviewed_files,
        "drive_receipt_file_id": required_text(receipt.get("drive_receipt_file_id"), "drive_receipt_file_id"),
    }


def stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--os-root", required=True)
    parser.add_argument("--os-port", type=int, default=18087)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace_root).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace does not exist: {workspace}")
    request = load_request(Path(args.request).expanduser().resolve())
    job_id = required_text(request.get("job_id"), "job_id")
    expected_delivery_id = str(request.get("delivery_id", "") or "").strip()
    expected_revision = request.get("delivery_revision")
    required_kinds = [str(v).strip() for v in request.get("required_kinds", []) if str(v).strip()]
    required_paths = [str(v).strip().replace("\\", "/") for v in request.get("required_paths", []) if str(v).strip()]
    review_provenance = load_review_provenance(request, workspace)

    process: subprocess.Popen[bytes] | None = None
    try:
        process, os_url, stdout_path, stderr_path = start_isolated_os(
            Path(args.os_root).expanduser().resolve(), workspace, args.os_port
        )
        client = EngineeringOSClient(EngineeringOSConfig(base_url=os_url, timeout_seconds=30.0))
        latest = client.latest_delivery(job_id)
        approval = client.approval_status(job_id)
    finally:
        stop(process)
    if approval.get("approved") is not True:
        raise RuntimeError("Engineering OS approval_status is not approved during final delivery validation")

    delivery_id = required_text(latest.get("id") or latest.get("delivery_id"), "latest delivery id")
    revision = latest.get("revision")
    if expected_delivery_id and delivery_id != expected_delivery_id:
        raise RuntimeError(f"delivery id mismatch: expected {expected_delivery_id}, got {delivery_id}")
    if expected_revision not in (None, "") and str(revision) != str(expected_revision):
        raise RuntimeError(f"delivery revision mismatch: expected {expected_revision}, got {revision}")
    if str(latest.get("status", "")).strip().lower() != "published":
        raise RuntimeError(f"latest delivery is not published: {latest.get('status')!r}")

    package_path = bounded(Path(required_text(latest.get("root_path"), "delivery.root_path")), workspace, "delivery root")
    manifest_path = bounded(Path(required_text(latest.get("manifest_path"), "delivery.manifest_path")), workspace, "delivery manifest")
    website_path = bounded(Path(required_text(latest.get("website_entry"), "delivery.website_entry")), workspace, "delivery website")
    for path, label in ((package_path, "delivery root"), (manifest_path, "delivery manifest"), (website_path, "delivery website")):
        if label == "delivery root":
            if not path.is_dir():
                raise RuntimeError(f"{label} missing: {path}")
        elif not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"{label} missing/empty: {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "delivery-manifest/1.0":
        raise RuntimeError("delivery manifest schema mismatch")
    if str(manifest.get("delivery_id", "")) != delivery_id:
        raise RuntimeError("delivery manifest id mismatch")
    if str(manifest.get("job_id", "")) != job_id:
        raise RuntimeError("delivery manifest job mismatch")
    if str(manifest.get("revision", "")) != str(revision):
        raise RuntimeError("delivery manifest revision mismatch")
    if str(manifest.get("status", "")).lower() != "published":
        raise RuntimeError("delivery manifest is not published")

    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("delivery manifest has no items")
    verified: list[dict[str, Any]] = []
    kinds: set[str] = set()
    relpaths: set[str] = set()
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise RuntimeError(f"delivery item {index} must be an object")
        rel = required_text(raw.get("delivery_path"), f"items[{index}].delivery_path").replace("\\", "/")
        item_path = bounded(package_path / Path(rel.replace("/", os.sep)), package_path, f"delivery item {index}")
        if not item_path.is_file():
            raise RuntimeError(f"delivery item missing: {item_path}")
        size = item_path.stat().st_size
        expected_size = int(raw.get("size", -1))
        if size != expected_size:
            raise RuntimeError(f"delivery item size mismatch for {rel}: expected {expected_size}, got {size}")
        actual_sha = sha256_file(item_path)
        expected_sha = required_text(raw.get("sha256"), f"items[{index}].sha256").lower()
        if actual_sha != expected_sha:
            raise RuntimeError(f"delivery item SHA256 mismatch for {rel}")
        kind = str(raw.get("kind", "") or "").strip()
        if kind:
            kinds.add(kind)
        relpaths.add(rel)
        verified.append({"path": str(item_path), "delivery_path": rel, "kind": kind, "size": size, "sha256": actual_sha})

    missing_kinds = [kind for kind in required_kinds if kind not in kinds]
    if missing_kinds:
        raise RuntimeError("delivery is missing required artifact kinds: " + ", ".join(missing_kinds))
    missing_paths = [rel for rel in required_paths if rel not in relpaths and not (package_path / Path(rel.replace("/", os.sep))).exists()]
    if missing_paths:
        raise RuntimeError("delivery is missing required paths: " + ", ".join(missing_paths))

    checksum_manifest_path = package_path / "checksum-manifest.json"
    if not checksum_manifest_path.is_file() or checksum_manifest_path.stat().st_size <= 0:
        raise RuntimeError("checksum-manifest.json missing/empty")
    checksum_manifest = json.loads(checksum_manifest_path.read_text(encoding="utf-8-sig"))
    if checksum_manifest.get("schema_version") != "checksum-manifest/1.0":
        raise RuntimeError("checksum manifest schema mismatch")
    checks = checksum_manifest.get("items")
    if not isinstance(checks, list) or len(checks) != len(items):
        raise RuntimeError("checksum manifest item count mismatch")

    output = {
        "schema_version": "openworker-final-delivery-validation/v2",
        "status": "PASS",
        "job_id": job_id,
        "delivery_id": delivery_id,
        "delivery_revision": revision,
        "package_path": str(package_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "website_path": str(website_path),
        "website_sha256": sha256_file(website_path),
        "checksum_manifest_path": str(checksum_manifest_path),
        "checksum_manifest_sha256": sha256_file(checksum_manifest_path),
        "item_count": len(verified),
        "verified_items": verified,
        "required_kinds": required_kinds,
        "required_paths": required_paths,
        "review_provenance": review_provenance,
        "engineering_os_approval_status": approval,
        "runner": os.environ.get("COMPUTERNAME", ""),
        "github_action_used_for_business_execution": False,
        "os_stdout": str(stdout_path),
        "os_stderr": str(stderr_path),
    }
    evidence = bounded(Path(args.evidence), workspace, "final validation evidence")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    temp = evidence.with_suffix(".tmp")
    temp.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, evidence)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"OPENWORKER_FINAL_DELIVERY_VALIDATION_PASS delivery={delivery_id} evidence={evidence}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"OPENWORKER_FINAL_DELIVERY_VALIDATION_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
