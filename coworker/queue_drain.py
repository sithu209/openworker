"""One-call, idempotent queue drain for OpenWorker.

OpenWorker owns the operator UX: a caller asks once to drain one go-tool capability.
The go-tool-runtime queue administrator remains the execution authority.  Success is
returned only after go-tool reports ``clean=true``; repeated calls against an already
clean queue are therefore safe.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


class QueueDrainError(RuntimeError):
    """Raised when a requested queue cannot be proven clean."""


def _runtime_root(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_root = os.environ.get("OPENWORKER_GO_TOOL_RUNTIME_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    if os.name == "nt":
        candidates.append(Path(r"D:\AI-Tools\AI Tool Runtime"))
    candidates.append(Path.cwd())

    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / "config.yaml").is_file() and (root / "cmd" / "gtr-actions-queue").is_dir():
            return root
    raise QueueDrainError(
        "go-tool-runtime root not found; set OPENWORKER_GO_TOOL_RUNTIME_ROOT"
    )


def _decode_report(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise QueueDrainError("go-tool queue drain returned no JSON report")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        # Keep the error bounded; credentials or runner paths must not be dumped wholesale.
        raise QueueDrainError(f"invalid go-tool queue report: {text[-500:]}") from exc
    if not isinstance(payload, dict):
        raise QueueDrainError("go-tool queue report root must be an object")
    return payload


def drain_queue(
    capability_id: str,
    *,
    runtime_root: str | None = None,
    timeout_seconds: int = 120,
    verify_seconds: int = 30,
    retry_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Drain one go-tool capability queue and return only after it is proven clean.

    This function is intentionally idempotent.  Calling it repeatedly is valid, including
    when the target queue is already empty.  The caller does not need to query/cancel/verify
    separately; those operations are owned by go-tool-runtime's queue administrator.
    """
    capability = capability_id.strip()
    if not capability:
        raise QueueDrainError("capability_id is required")
    if timeout_seconds <= 0:
        raise QueueDrainError("timeout_seconds must be positive")
    if verify_seconds <= 0:
        raise QueueDrainError("verify_seconds must be positive")

    root = _runtime_root(runtime_root)
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, Any]] = []

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise QueueDrainError(
                f"queue drain timed out before clean=true for capability {capability!r}"
            )

        command = [
            "go",
            "run",
            "./cmd/gtr-actions-queue",
            "--config",
            "config.yaml",
            "--capability",
            capability,
            "--workflow-scoped=true",
            "--cancel-active=true",
            f"--verify-seconds={min(verify_seconds, max(1, int(remaining)))}",
        ]
        proc = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=max(1, int(remaining)),
            check=False,
        )
        report = _decode_report(proc.stdout)
        attempts.append(
            {
                "returncode": proc.returncode,
                "clean": bool(report.get("clean")),
                "cancelled": report.get("cancelled", []),
                "still_active": report.get("still_active", []),
                "errors": report.get("errors", []),
            }
        )

        if bool(report.get("clean")) and not report.get("still_active"):
            return {
                "schema_version": "openworker-queue-drain/v1",
                "capability_id": capability,
                "clean": True,
                "attempt_count": len(attempts),
                "cancelled": report.get("cancelled", []),
                "preserved": report.get("preserved", []),
                "remaining_active": [],
                "go_tool_report": report,
            }

        if time.monotonic() >= deadline:
            raise QueueDrainError(
                f"queue drain failed closed for {capability!r}: remaining active runs exist"
            )
        time.sleep(max(0.0, retry_interval_seconds))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openworker queue-drain",
        description="Drain one go-tool capability queue in one idempotent call.",
    )
    parser.add_argument("--capability", required=True, dest="capability_id")
    parser.add_argument("--runtime-root")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--verify-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        report = drain_queue(
            args.capability_id,
            runtime_root=args.runtime_root,
            timeout_seconds=args.timeout_seconds,
            verify_seconds=args.verify_seconds,
        )
    except Exception as exc:
        print(json.dumps({"clean": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
