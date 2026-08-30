"""Command-line evidence verification for Harness H8/H9 real local runs."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

from .comfyx_long_job import ComfyXLongJobError, verify_with_engineering_os
from .engineering_os import EngineeringOSClient, EngineeringOSConfig, EngineeringOSError
from .runtime_ab import RuntimeABError, fingerprint_artifacts


def _client(args: argparse.Namespace) -> EngineeringOSClient:
    return EngineeringOSClient(
        EngineeringOSConfig(base_url=args.os_url, timeout_seconds=args.timeout)
    )


def _rc_evidence(client: EngineeringOSClient, project_id: str, job_id: str, strict: bool) -> dict[str, Any]:
    job = client.get_job(job_id)
    if job.get("project_id") != project_id:
        raise RuntimeABError(
            f"job {job_id} belongs to {job.get('project_id')!r}, expected {project_id!r}"
        )
    status = str(job.get("status") or "")
    if status not in {"review", "completed", "published"}:
        raise RuntimeABError(f"job {job_id} is not an acceptable terminal RC evidence state: {status}")
    artifacts = client.list_job_artifacts(job_id)
    fingerprints = fingerprint_artifacts(artifacts, strict_checksums=strict)
    families = Counter(item.family for item in fingerprints)
    for required in ("calculation", "drawing", "bim"):
        if families[required] <= 0:
            raise RuntimeABError(f"job {job_id} missing {required} artifact family")
    return {
        "project_id": project_id,
        "job_id": job_id,
        "status": status,
        "fingerprints": [item.__dict__ for item in fingerprints],
        "family_counts": dict(families),
    }


def _cmd_rc_compare(args: argparse.Namespace) -> dict[str, Any]:
    client = _client(args)
    native = _rc_evidence(client, args.native_project, args.native_job, args.strict_checksums)
    harness = _rc_evidence(client, args.harness_project, args.harness_job, args.strict_checksums)
    equivalent = native["fingerprints"] == harness["fingerprints"]
    report = {
        "verification": "h8-rc-evidence-comparison",
        "strict_checksums": args.strict_checksums,
        "native": native,
        "harness": harness,
        "equivalent": equivalent,
    }
    if not equivalent:
        raise RuntimeABError("Native/Harness authoritative RC artifact evidence differs")
    return report


def _cmd_comfyx(args: argparse.Namespace) -> dict[str, Any]:
    report = verify_with_engineering_os(
        _client(args), project_id=args.project, job_id=args.job
    )
    return {"verification": "h9-comfyx-media-evidence", **report.to_dict()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openworker-harness-evidence",
        description="Verify H8 RC A/B evidence or H9 ComfyX MP4 evidence from AI-Engineering-OS.",
    )
    parser.add_argument("--os-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=30.0)
    sub = parser.add_subparsers(dest="command", required=True)

    rc = sub.add_parser("rc-compare", help="compare two already-executed authoritative RC jobs")
    rc.add_argument("--native-project", required=True)
    rc.add_argument("--native-job", required=True)
    rc.add_argument("--harness-project", required=True)
    rc.add_argument("--harness-job", required=True)
    rc.add_argument("--strict-checksums", action="store_true")
    rc.set_defaults(func=_cmd_rc_compare)

    media = sub.add_parser("comfyx-verify", help="verify one Engineering-OS/ComfyX media job")
    media.add_argument("--project", required=True)
    media.add_argument("--job", required=True)
    media.set_defaults(func=_cmd_comfyx)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.func(args)
    except (RuntimeABError, ComfyXLongJobError, EngineeringOSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "succeeded", "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
