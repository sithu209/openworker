"""Durable user-approval control for Case 0005.

Approval is a supervisor control action, not a media worker.  It verifies the
exact PPTX the user reviewed against both durable parent evidence and physical
workspace bytes before passing approval gates 0005-027 / 0005-057.  Passing a
gate immediately wakes the local Case 0005 controller; GitHub is not involved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from .case0005_controller import Case0005Controller
from .case_worklist import CaseWorklistError, StepStatus
from .case_worklist_runtime import CaseWorklistRuntime

_APPROVAL_ACTION = "openworker.user.approval"
_GATE_CONFIG: dict[str, dict[str, str]] = {
    "0005-027": {
        "parent_step": "0005-025",
        "artifact_key": "storyboard_pptx",
        "sha_key": "storyboard_pptx_sha256",
        "accepted_sha_key": "approved_storyboard_pptx_sha256",
    },
    "0005-057": {
        "parent_step": "0005-055",
        "artifact_key": "illustrated_storyboard_pptx",
        "sha_key": "illustrated_storyboard_sha256",
        "accepted_sha_key": "approved_illustrated_storyboard_sha256",
    },
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def approve(
    workspace: str | Path,
    *,
    step_id: str,
    approved_sha256: str,
    actor: str = "user",
    node_url: str = "http://127.0.0.1:8787",
) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    config = _GATE_CONFIG.get(step_id)
    if config is None:
        raise CaseWorklistError("Case 0005 approval only supports steps 0005-027 and 0005-057")
    approved_sha = approved_sha256.strip().lower()
    if len(approved_sha) != 64 or any(ch not in "0123456789abcdef" for ch in approved_sha):
        raise CaseWorklistError("approved_sha256 must be 64 lowercase/uppercase hex characters")
    actor = actor.strip()
    if not actor:
        raise CaseWorklistError("approval actor is required")

    runtime = CaseWorklistRuntime(root)
    worklist = runtime.load()
    if worklist.case_id != "0005":
        raise CaseWorklistError(f"approval workspace is not Case 0005: {worklist.case_id!r}")
    gate = worklist.step(step_id)
    if gate.kind != "approval" or gate.allowed_actions != [_APPROVAL_ACTION]:
        raise CaseWorklistError(f"step {step_id} is not the canonical Case 0005 approval gate")
    worklist.assert_action_allowed(step_id, _APPROVAL_ACTION)
    if gate.status != StepStatus.READY:
        raise CaseWorklistError(f"approval gate {step_id} must be READY, got {gate.status.value}")

    parent = worklist.step(config["parent_step"])
    artifact_raw = str(parent.evidence.get(config["artifact_key"], "")).strip()
    durable_sha = str(parent.evidence.get(config["sha_key"], "")).strip().lower()
    if not artifact_raw or len(durable_sha) != 64:
        raise CaseWorklistError(f"parent {parent.step_id} lacks durable PPTX path/SHA evidence")
    artifact = Path(artifact_raw)
    if not artifact.is_absolute():
        artifact = root / artifact
    artifact = artifact.resolve()
    try:
        artifact.relative_to(root)
    except ValueError as exc:
        raise CaseWorklistError("approval artifact escapes Case workspace") from exc
    if not artifact.is_file() or artifact.stat().st_size <= 0:
        raise CaseWorklistError("approval artifact is missing or empty")
    physical_sha = _sha256_file(artifact)
    if physical_sha != durable_sha:
        raise CaseWorklistError(
            f"approval artifact physical SHA mismatch durable={durable_sha} physical={physical_sha}"
        )
    if approved_sha != durable_sha:
        raise CaseWorklistError(
            f"user-approved SHA mismatch reviewed={approved_sha} durable={durable_sha}"
        )

    execution_id = f"case0005-{step_id}-approval-{durable_sha[:16]}"
    receipt_path = root / "evidence" / f"{step_id}-user-approval.json"
    receipt = {
        "schema_version": "openworker-case0005-user-approval/v1",
        "case_id": "0005",
        "step_id": step_id,
        "action_id": _APPROVAL_ACTION,
        "execution_id": execution_id,
        "approval_decision": "approved",
        "approved_by": actor,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "artifact": str(artifact),
        "artifact_sha256": durable_sha,
        "physical_sha256_verified": True,
    }
    _write_json_atomic(receipt_path, receipt)

    runtime.start_action(step_id, _APPROVAL_ACTION, execution_id=execution_id)
    evidence = {
        config["accepted_sha_key"]: durable_sha,
        "approval_decision": "approved",
        "approval_receipt": str(receipt_path),
    }
    try:
        runtime.accept_action_evidence(
            step_id,
            _APPROVAL_ACTION,
            execution_id=execution_id,
            evidence=evidence,
        )
    except Exception:
        try:
            runtime.block_active(step_id, "approval persistence failed after verified user decision")
        except Exception:
            pass
        raise

    downstream = Case0005Controller(root, node_url=node_url).dispatch_ready()
    return {
        "status": "approved",
        "case_id": "0005",
        "step_id": step_id,
        "artifact": str(artifact),
        "sha256": durable_sha,
        "approval_receipt": str(receipt_path),
        "downstream": downstream,
        "github_action_used_for_business_execution": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approve a verified Case 0005 storyboard gate locally")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--step-id", required=True, choices=sorted(_GATE_CONFIG))
    parser.add_argument("--approved-sha256", required=True)
    parser.add_argument("--actor", default="user")
    parser.add_argument("--node-url", default="http://127.0.0.1:8787")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = approve(
            args.workspace,
            step_id=args.step_id,
            approved_sha256=args.approved_sha256,
            actor=args.actor,
            node_url=args.node_url,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
