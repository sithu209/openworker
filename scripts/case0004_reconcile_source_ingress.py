from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from coworker.case_worklist import CaseWorklistError, StepStatus
from coworker.case_worklist_runtime import CaseWorklistRuntime
from coworker.runtimes.job_binding import JobBindingStore

CASE_ID = "0004"
PARENT_STEP_ID = "0004-020"
REPAIR_STEP_ID = "R-0004-020-003"
REPAIR_ACTION = "openworker.source.ingress.reconcile"
PARENT_ACTION = "openworker.source.ingress"
EXPECTED_HOST = "DESKTOP-O87PJNR"
EXPECTED_SIZE = 1_385_583
EXPECTED_SHA256 = "aaadbd84e8a5b2e1b0b8f54c16901a69085c7501aeec602929fd994f3192f5b6"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise CaseWorklistError(f"JSON root must be an object: {path}")
    return raw


def _pick_existing_ingress_evidence(workspace: Path) -> tuple[Path, dict]:
    root = workspace / "evidence" / "source-ingress"
    if not root.is_dir():
        raise CaseWorklistError(f"source ingress evidence directory missing: {root}")
    candidates = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = _load_json(path)
        except (OSError, ValueError, CaseWorklistError):
            continue
        if str(payload.get("sha256", "")).lower() != EXPECTED_SHA256:
            continue
        if not str(payload.get("project_id", "")).strip() or not str(payload.get("job_id", "")).strip():
            continue
        canonical_raw = str(payload.get("canonical_path", "")).strip()
        if not canonical_raw:
            continue
        canonical = Path(canonical_raw).expanduser().resolve()
        if not canonical.is_file():
            continue
        if canonical.stat().st_size != EXPECTED_SIZE or _sha256(canonical) != EXPECTED_SHA256:
            continue
        return path.resolve(), payload
    raise CaseWorklistError("no existing successful source-ingress evidence matches the canonical DWG")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Case 0004 source-ingress governance from existing REAL evidence")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--execution-id", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace_root).expanduser().resolve()
    actual_host = JobBindingStore.current_host().strip()
    if actual_host.casefold() != EXPECTED_HOST.casefold():
        raise CaseWorklistError(f"wrong fixed host: expected {EXPECTED_HOST}, got {actual_host or '<unknown>'}")

    runtime = CaseWorklistRuntime(workspace)
    worklist = runtime.load()
    if worklist.case_id != CASE_ID:
        raise CaseWorklistError(f"wrong case worklist: expected {CASE_ID}, got {worklist.case_id}")

    parent = worklist.step(PARENT_STEP_ID)
    if parent.status == StepStatus.PASSED:
        print("CASE0004_020_ALREADY_PASSED")
        return 0
    if parent.status != StepStatus.BLOCKED:
        raise CaseWorklistError(f"{PARENT_STEP_ID} must be BLOCKED before reconciliation, got {parent.status.value}")

    if not any(step.step_id == REPAIR_STEP_ID for step in worklist.steps):
        runtime.add_repair(
            parent_step_id=PARENT_STEP_ID,
            step_id=REPAIR_STEP_ID,
            title="Reconcile successful REAL ingress evidence and missing JobBinding path",
            allowed_actions=[REPAIR_ACTION],
            acceptance=["source_ingress_evidence", "job_binding_path", "canonical_sha256"],
        )

    execution_id = args.execution_id.strip()
    runtime.start_action(REPAIR_STEP_ID, REPAIR_ACTION, execution_id=execution_id)

    evidence_path, ingress = _pick_existing_ingress_evidence(workspace)
    canonical = Path(str(ingress["canonical_path"])).expanduser().resolve()
    canonical_sha = _sha256(canonical)

    binding_store = JobBindingStore(workspace)
    binding = binding_store.load()
    if binding is None:
        raise CaseWorklistError(f"JobBinding missing: {binding_store.path}")
    if binding.assigned_host.casefold() != EXPECTED_HOST.casefold():
        raise CaseWorklistError(f"JobBinding host mismatch: {binding.assigned_host}")
    if binding.project_id != str(ingress["project_id"]) or binding.job_id != str(ingress["job_id"]):
        raise CaseWorklistError(
            "JobBinding identity mismatch with successful ingress evidence: "
            f"binding=({binding.project_id},{binding.job_id}) evidence=({ingress['project_id']},{ingress['job_id']})"
        )

    runtime.record(REPAIR_STEP_ID, "source_ingress_evidence", str(evidence_path))
    runtime.record(REPAIR_STEP_ID, "job_binding_path", str(binding_store.path))
    runtime.record(REPAIR_STEP_ID, "canonical_sha256", canonical_sha)
    runtime.complete_action(REPAIR_STEP_ID, REPAIR_ACTION, execution_id=execution_id)
    runtime.pass_step(REPAIR_STEP_ID)

    # The repair intentionally does not copy/ingest the DWG again. It re-opens the
    # parent governance step and replays only acceptance bookkeeping from the
    # already verified physical artifact, ingress receipt, and JobBinding.
    parent_execution = execution_id + ":parent-acceptance"
    runtime.start_action(PARENT_STEP_ID, PARENT_ACTION, execution_id=parent_execution)
    run_id = str(ingress.get("github_run_id", "") or ingress.get("source_run_id", "") or "existing-real-ingress")
    runtime.record(PARENT_STEP_ID, "run_id", run_id)
    runtime.record(PARENT_STEP_ID, "project_id", str(ingress["project_id"]))
    runtime.record(PARENT_STEP_ID, "job_id", str(ingress["job_id"]))
    runtime.record(PARENT_STEP_ID, "canonical_path", str(canonical))
    runtime.record(PARENT_STEP_ID, "sha256", canonical_sha)
    runtime.record(PARENT_STEP_ID, "job_binding_path", str(binding_store.path))
    runtime.record(PARENT_STEP_ID, "reconciliation_repair", REPAIR_STEP_ID)
    runtime.record(PARENT_STEP_ID, "reconciliation_evidence", str(evidence_path))
    runtime.complete_action(PARENT_STEP_ID, PARENT_ACTION, execution_id=parent_execution)
    runtime.pass_step(PARENT_STEP_ID)

    final = runtime.load()
    print(
        "CASE0004_SOURCE_INGRESS_RECONCILED "
        f"repair={REPAIR_STEP_ID} parent={PARENT_STEP_ID} "
        f"canonical={canonical} size={canonical.stat().st_size} sha256={canonical_sha} "
        f"job_binding={binding_store.path} next={final.as_dict()['canonical_next_step_id']}"
    )
    if final.as_dict()["canonical_next_step_id"] != "0004-030":
        raise CaseWorklistError(
            f"unexpected canonical next step after reconciliation: {final.as_dict()['canonical_next_step_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
