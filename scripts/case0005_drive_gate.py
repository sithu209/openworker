"""Wait for and apply one bounded Case 0005 Google Drive gate receipt.

This is review transport only, never command ingress. The only accepted cloud file is
an exact JSON filename inside the already-authoritative revision folder emitted by the
local publisher. It cannot contain shell commands, tool names, paths to execute, or
arbitrary next-step instructions.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from coworker.case_worklist import CaseWorklistError, StepStatus
from coworker.case_worklist_runtime import CaseWorklistRuntime
from coworker.engineering.engineering_os import EngineeringOSClient, EngineeringOSConfig
from coworker.review_drive import ReviewDriveError
from coworker.review_drive_receipt import GoogleDriveReviewReceiptClient
from coworker.work_ledger import WorkLedger
from scripts.engineering_source_ingress_action import start_isolated_os

SCHEMA = "openworker-case0005-drive-gate-receipt/v1"
CASE_ID = "0005"
GATES = {
    "0005-027": {"publish_step": "0005-026", "decision": "APPROVE", "kind": "storyboard-text"},
    "0005-057": {"publish_step": "0005-056", "decision": "APPROVE", "kind": "storyboard-illustrated"},
    "0005-100": {"publish_step": "0005-090", "decision": "PASS", "kind": "final-review"},
}


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"{name} is required")
    return text


def _safe_id(value: Any, name: str) -> str:
    text = _required(value, name)
    if any(ch in text for ch in "/\\?#"):
        raise RuntimeError(f"{name} contains invalid path characters")
    return text


def _publish_evidence(worklist, publish_step: str) -> Mapping[str, Any]:
    step = worklist.step(publish_step)
    if step.status != StepStatus.PASSED:
        raise RuntimeError(f"publish step {publish_step} is not PASSED: {step.status.value}")
    return step.evidence


def _expected_files(evidence: Mapping[str, Any]) -> list[dict[str, str]]:
    paths = evidence.get("published_artifacts")
    shas = evidence.get("published_artifact_sha256")
    ids = evidence.get("drive_file_ids")
    if not isinstance(paths, list) or not isinstance(shas, list) or not isinstance(ids, list):
        raise RuntimeError("publish evidence is missing artifact path/SHA/Drive ID arrays")
    if not paths or len(paths) != len(shas) or len(paths) != len(ids):
        raise RuntimeError("publish evidence artifact path/SHA/Drive ID arrays are inconsistent")
    result: list[dict[str, str]] = []
    for index, (path, sha, file_id) in enumerate(zip(paths, shas, ids)):
        p = _required(path, f"published_artifacts[{index}]").replace("\\", "/")
        digest = _required(sha, f"published_artifact_sha256[{index}]").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError(f"published artifact SHA256 is invalid at index {index}")
        result.append({"relative_path": p, "sha256": digest, "drive_file_id": _safe_id(file_id, f"drive_file_ids[{index}]")})
    return result


def _validate_receipt(
    raw: Mapping[str, Any],
    *,
    step_id: str,
    folder_id: str,
    manifest_sha: str,
    expected_files: list[dict[str, str]],
    expected_workledger_revision_id: str = "",
) -> tuple[str, str]:
    if str(raw.get("schema_version") or "") != SCHEMA:
        raise RuntimeError("Drive gate receipt schema mismatch")
    if str(raw.get("case_id") or "") != CASE_ID:
        raise RuntimeError("Drive gate receipt case_id mismatch")
    if str(raw.get("step_id") or "") != step_id:
        raise RuntimeError("Drive gate receipt step_id mismatch")
    if str(raw.get("drive_revision_folder_id") or "") != folder_id:
        raise RuntimeError("Drive gate receipt folder identity mismatch")
    if str(raw.get("bundle_manifest_sha256") or "").strip().lower() != manifest_sha.lower():
        raise RuntimeError("Drive gate receipt bundle manifest SHA mismatch")
    if raw.get("commands") is not None or raw.get("command") is not None or raw.get("tool") is not None:
        raise RuntimeError("Drive gate receipt must not contain command/tool fields")
    if step_id == "0005-100":
        actual_revision = _safe_id(raw.get("workledger_revision_id"), "workledger_revision_id")
        if actual_revision != _safe_id(expected_workledger_revision_id, "expected WorkLedger revision id"):
            raise RuntimeError("Drive final review receipt WorkLedger revision identity mismatch")

    reviewed = raw.get("reviewed_files")
    if not isinstance(reviewed, list) or len(reviewed) != len(expected_files):
        raise RuntimeError("Drive gate receipt reviewed_files does not cover the exact published artifact set")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(reviewed):
        if not isinstance(item, Mapping):
            raise RuntimeError(f"reviewed_files[{index}] must be an object")
        normalized.append({
            "relative_path": _required(item.get("relative_path"), f"reviewed_files[{index}].relative_path").replace("\\", "/"),
            "sha256": _required(item.get("sha256"), f"reviewed_files[{index}].sha256").lower(),
            "drive_file_id": _safe_id(item.get("drive_file_id"), f"reviewed_files[{index}].drive_file_id"),
        })
    key = lambda item: (item["relative_path"].lower(), item["sha256"], item["drive_file_id"])
    if sorted(map(key, normalized)) != sorted(map(key, expected_files)):
        raise RuntimeError("Drive gate receipt reviewed file identities do not match local publication evidence")

    decision = _required(raw.get("decision"), "decision").upper()
    reviewer = _required(raw.get("reviewer"), "reviewer")
    allowed = {"0005-027": {"APPROVE", "REJECT"}, "0005-057": {"APPROVE", "REJECT"}, "0005-100": {"PASS", "REWORK"}}[step_id]
    if decision not in allowed:
        raise RuntimeError(f"unsupported decision {decision!r} for {step_id}")
    return decision, reviewer


def _wait_receipt(client: GoogleDriveReviewReceiptClient, *, folder_id: str, filename: str,
                  timeout_seconds: int, poll_seconds: float) -> tuple[Mapping[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        found = client.fetch_exact_json(parent_id=folder_id, name=filename)
        if found is not None:
            return found
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for Drive gate receipt {filename!r}")
        time.sleep(poll_seconds)


def _stop(process) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except Exception:
        process.kill()


def _apply_final_pass(workspace: Path, os_root: Path, worklist, reviewer: str, comment: str) -> tuple[str, dict[str, Any]]:
    revision_id = _required(worklist.step("0005-080").evidence.get("revision_id"), "WorkLedger revision_id")
    job_id = _safe_id(worklist.step("0005-082").evidence.get("job_id"), "Engineering OS job_id")
    artifact_ids = worklist.step("0005-085").evidence.get("artifact_ids")
    if not isinstance(artifact_ids, list) or not artifact_ids:
        raise RuntimeError("0005-085 artifact_ids are unavailable")

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        accepted = ledger.accept_revision(revision_id)
        accepted_revision_id = _required(accepted.get("revision_id"), "accepted revision id")
    finally:
        ledger.close()

    process = None
    try:
        process, os_url, _stdout, _stderr = start_isolated_os(os_root, workspace, 18088)
        client = EngineeringOSClient(EngineeringOSConfig(base_url=os_url, timeout_seconds=30.0))
        applied: list[dict[str, Any]] = []
        for raw_id in artifact_ids:
            artifact_id = _safe_id(raw_id, "Engineering OS artifact_id")
            existing = client.list_artifact_reviews(artifact_id)
            already = next((item for item in existing if str(item.get("reviewer") or "") == reviewer and str(item.get("decision") or "") == "approved"), None)
            if already is None:
                already = client.submit_artifact_review(
                    job_id=job_id,
                    artifact_id=artifact_id,
                    reviewer=reviewer,
                    decision="approved",
                    comment=comment,
                )
            applied.append(dict(already))
        approval = client.approval_status(job_id)
        if approval.get("approved") is not True:
            raise RuntimeError("Engineering OS approval_status is not approved after ChatGPT PASS")
        return accepted_revision_id, {"job_id": job_id, "artifact_reviews": applied, "approval_status": approval}
    finally:
        _stop(process)


def _write_local_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--step-id", required=True, choices=sorted(GATES))
    parser.add_argument("--os-root")
    parser.add_argument("--timeout-seconds", type=int, default=43200)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace unavailable: {workspace}")
    runtime = CaseWorklistRuntime(workspace)
    worklist = runtime.load()
    if worklist.case_id != CASE_ID:
        raise RuntimeError(f"unexpected Case id: {worklist.case_id}")
    step = worklist.step(args.step_id)
    if step.status not in {StepStatus.READY, StepStatus.RUNNING}:
        raise RuntimeError(f"gate step {args.step_id} is not ready/running: {step.status.value}")

    gate = GATES[args.step_id]
    publish = _publish_evidence(worklist, gate["publish_step"])
    folder_id = _safe_id(publish.get("drive_folder_id"), "drive_folder_id")
    manifest_sha = _required(publish.get("manifest_sha256"), "bundle manifest SHA").lower()
    expected_files = _expected_files(publish)
    expected_revision_id = ""
    if args.step_id == "0005-100":
        expected_revision_id = _safe_id(worklist.step("0005-080").evidence.get("revision_id"), "WorkLedger revision_id")
    filename = f"case0005-{args.step_id}-receipt.json"

    drive = GoogleDriveReviewReceiptClient.from_environment()
    try:
        identity, raw = _wait_receipt(
            drive,
            folder_id=folder_id,
            filename=filename,
            timeout_seconds=max(1, args.timeout_seconds),
            poll_seconds=max(1.0, args.poll_seconds),
        )
    finally:
        drive.close()

    decision, reviewer = _validate_receipt(
        raw,
        step_id=args.step_id,
        folder_id=folder_id,
        manifest_sha=manifest_sha,
        expected_files=expected_files,
        expected_workledger_revision_id=expected_revision_id,
    )
    comment = str(raw.get("comment") or "").strip()
    local_receipt = workspace / ".openworker" / "review-receipts" / filename
    local_payload = dict(raw)
    local_payload["drive_receipt_file_id"] = _safe_id(identity.get("id"), "Drive gate receipt file id")

    if args.step_id in {"0005-027", "0005-057"}:
        if decision != "APPROVE":
            _write_local_receipt(local_receipt, local_payload)
            raise RuntimeError(f"storyboard gate decision is {decision}; generation remains blocked: {comment}")
        digest = expected_files[0]["sha256"]
        if args.step_id == "0005-027":
            evidence = {
                "approved_storyboard_pptx_sha256": digest,
                "approval_decision": "APPROVE",
                "approval_receipt": str(local_receipt),
            }
        else:
            evidence = {
                "approved_illustrated_storyboard_sha256": digest,
                "approval_decision": "APPROVE",
                "approval_receipt": str(local_receipt),
            }
    else:
        if decision != "PASS":
            _write_local_receipt(local_receipt, local_payload)
            revision_id = _required(worklist.step("0005-080").evidence.get("revision_id"), "WorkLedger revision_id")
            ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
            try:
                ledger.request_rework(revision_id, reason=comment or "ChatGPT requested rework")
            finally:
                ledger.close()
            raise RuntimeError(f"final review decision is {decision}; WorkLedger marked REWORK_REQUIRED")
        if not args.os_root:
            raise RuntimeError("--os-root is required for final review PASS")
        accepted_revision_id, os_review = _apply_final_pass(
            workspace,
            Path(args.os_root).expanduser().resolve(),
            worklist,
            reviewer,
            comment or "ChatGPT reviewed Drive-published physical artifacts and approved them",
        )
        local_payload["accepted_revision_id"] = accepted_revision_id
        evidence = {
            "review_receipt": str(local_receipt),
            "review_decision": "PASS",
            "accepted_revision_id": accepted_revision_id,
            "engineering_os_review": os_review,
        }

    _write_local_receipt(local_receipt, local_payload)
    output = {
        "schema_version": "openworker-case0005-drive-gate-result/v1",
        "case_id": CASE_ID,
        "step_id": args.step_id,
        "decision": decision,
        "reviewer": reviewer,
        "drive_revision_folder_id": folder_id,
        "drive_receipt_file_id": local_payload["drive_receipt_file_id"],
        "bundle_manifest_sha256": manifest_sha,
        "reviewed_files": expected_files,
        "local_receipt": str(local_receipt),
        "evidence": evidence,
        "github_action_used_for_business_execution": False,
        "cloud_command_ingress_used": False,
    }
    evidence_path = Path(args.evidence).expanduser().resolve()
    try:
        evidence_path.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError("gate evidence path escapes workspace") from exc
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = evidence_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, evidence_path)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ReviewDriveError, CaseWorklistError, TimeoutError) as exc:
        print(f"CASE0005_DRIVE_GATE_FAIL: {exc}", file=os.sys.stderr)
        raise SystemExit(2)
