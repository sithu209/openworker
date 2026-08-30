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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stop(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON root must be an object: {path}")
    return data


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"{name} is required")
    return text


def _register_artifacts(client: EngineeringOSClient, request: dict[str, Any], workspace: Path) -> dict[str, Any]:
    project_id = _required_text(request.get("project_id"), "project_id")
    job_id = _required_text(request.get("job_id"), "job_id")
    raw_items = request.get("artifacts")
    if not isinstance(raw_items, list) or not raw_items:
        raise RuntimeError("artifacts must be a non-empty array")

    registered: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise RuntimeError(f"artifacts[{index}] must be an object")
        path_raw = _required_text(raw.get("path"), f"artifacts[{index}].path")
        path = Path(path_raw).expanduser().resolve()
        try:
            path.relative_to(workspace)
        except ValueError as exc:
            raise RuntimeError(f"artifact path escapes workspace: {path}") from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"artifact missing or empty: {path}")
        actual_sha = _sha256(path)
        expected_sha = str(raw.get("sha256", "") or "").strip().lower()
        if expected_sha and expected_sha != actual_sha:
            raise RuntimeError(f"artifact SHA256 mismatch for {path}: expected {expected_sha}, got {actual_sha}")

        result = client.register_artifact(
            project_id=project_id,
            job_id=job_id,
            component_id=str(raw.get("component_id", "") or "").strip() or None,
            kind=_required_text(raw.get("kind"), f"artifacts[{index}].kind"),
            uri=str(path),
            media_type=_required_text(raw.get("media_type"), f"artifacts[{index}].media_type"),
            checksum=actual_sha,
            source_run_id=str(raw.get("source_run_id", "") or os.environ.get("GITHUB_RUN_ID", "")).strip() or None,
        )
        artifact_id = _required_text(result.get("id") or result.get("artifact_id"), "registered artifact id")
        registered.append(
            {
                "artifact_id": artifact_id,
                "kind": raw["kind"],
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": actual_sha,
                "response": result,
            }
        )

    current = client.list_job_artifacts(job_id)
    current_ids = {str(item.get("id") or item.get("artifact_id") or "").strip() for item in current}
    missing = [item["artifact_id"] for item in registered if item["artifact_id"] not in current_ids]
    if missing:
        raise RuntimeError("registered artifacts not visible in authoritative job registry: " + ", ".join(missing))

    revisions: list[dict[str, Any]] = []
    for item in current:
        artifact_id = str(item.get("id") or item.get("artifact_id") or "").strip()
        if artifact_id in current_ids and artifact_id:
            revisions.append(
                {
                    "artifact_id": artifact_id,
                    "revision": item.get("revision"),
                    "kind": item.get("kind"),
                    "checksum": item.get("checksum"),
                }
            )
    return {
        "action": "engineering_os.artifact.register",
        "project_id": project_id,
        "job_id": job_id,
        "artifact_ids": [item["artifact_id"] for item in registered],
        "current_revisions": revisions,
        "registered": registered,
    }


def _publish_delivery(client: EngineeringOSClient, request: dict[str, Any], workspace: Path) -> dict[str, Any]:
    job_id = _required_text(request.get("job_id"), "job_id")
    publisher = _required_text(request.get("publisher"), "publisher")
    approval = client.approval_status(job_id)
    if approval.get("approved") is not True:
        raise RuntimeError("AI-Engineering-OS approval_status is not approved")

    result = client.publish_job(job_id=job_id, publisher=publisher, note=str(request.get("note", "") or ""))
    delivery = result.get("delivery")
    website = result.get("website")
    if not isinstance(delivery, dict) or not isinstance(website, dict):
        raise RuntimeError("publish response does not contain delivery/website objects")
    delivery_id = _required_text(delivery.get("id") or delivery.get("delivery_id"), "delivery_id")
    manifest_path = Path(_required_text(delivery.get("manifest_path"), "delivery.manifest_path")).expanduser().resolve()
    website_path = Path(_required_text(website.get("path") or website.get("website_path"), "website.path")).expanduser().resolve()
    for path, label in ((manifest_path, "delivery manifest"), (website_path, "delivery website")):
        try:
            path.relative_to(workspace)
        except ValueError as exc:
            raise RuntimeError(f"{label} escapes workspace: {path}") from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"{label} missing or empty: {path}")

    latest = client.latest_delivery(job_id)
    latest_id = str(latest.get("id") or latest.get("delivery_id") or "").strip()
    if latest_id and latest_id != delivery_id:
        raise RuntimeError(f"latest delivery mismatch: published {delivery_id}, latest {latest_id}")
    revision = delivery.get("revision")
    if revision in (None, ""):
        revision = latest.get("revision")
    if revision in (None, ""):
        revision = delivery_id

    return {
        "action": "engineering_os.delivery.publish",
        "job_id": job_id,
        "delivery_id": delivery_id,
        "delivery_revision": revision,
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "website_path": str(website_path),
        "website_sha256": _sha256(website_path),
        "approval_status": approval,
        "delivery": delivery,
        "website": website,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["artifact-register", "delivery-publish"])
    parser.add_argument("--request", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--os-root", required=True)
    parser.add_argument("--os-port", type=int, default=18086)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace_root).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace does not exist: {workspace}")
    request = _load_json(Path(args.request).expanduser().resolve())

    process: subprocess.Popen[bytes] | None = None
    try:
        process, os_url, stdout_path, stderr_path = start_isolated_os(
            Path(args.os_root).expanduser().resolve(), workspace, args.os_port
        )
        client = EngineeringOSClient(EngineeringOSConfig(base_url=os_url, timeout_seconds=30.0))
        if args.action == "artifact-register":
            output = _register_artifacts(client, request, workspace)
        else:
            output = _publish_delivery(client, request, workspace)
        output.update(
            {
                "schema_version": "openworker-engineering-os-case-action/v1",
                "workspace_root": str(workspace),
                "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
                "runner": os.environ.get("COMPUTERNAME", ""),
                "os_stdout": str(stdout_path),
                "os_stderr": str(stderr_path),
            }
        )
    finally:
        _stop(process)

    evidence = Path(args.evidence).expanduser().resolve()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    temp = evidence.with_suffix(".tmp")
    temp.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, evidence)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"ENGINEERING_OS_CASE_ACTION_PASS action={output['action']} evidence={evidence}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ENGINEERING_OS_CASE_ACTION_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
