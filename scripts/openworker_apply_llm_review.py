"""Apply an immutable LLM review receipt to any OpenWorker WorkLedger work.

This is the generic governance entrypoint. It binds a receipt to the exact
review bundle, derives tuning policy from the immutable review request, and
advances only the reviewed work/revision. PASS accepts the revision; delivery
is optional and must be explicitly supplied by the caller.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from coworker.review_cycle import ReviewCycle
from coworker.review_gap import apply_review_finding
from coworker.work_ledger import WorkLedger


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} unavailable: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object: {path}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--work-code", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--delivery-json",
        default="",
        help="Optional JSON file. When supplied, PASS also moves delivered_revision_id.",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace unavailable: {workspace}")
    work_code = str(args.work_code).strip()
    revision_id = str(args.revision_id).strip()
    if not work_code or not revision_id:
        raise RuntimeError("work-code and revision-id are required")

    receipt_path = Path(args.receipt).expanduser().resolve()
    receipt = _load_json(receipt_path, label="review receipt")
    original_verdict = str(receipt.get("verdict") or "").strip().upper()

    request_path = workspace / ".openworker" / "reviews" / revision_id / "review-request.json"
    request = _load_json(request_path, label="review request")
    if str(request.get("revision_id") or "").strip() != revision_id:
        raise RuntimeError("review request revision_id mismatch")

    delivery: dict[str, Any] | None = None
    if str(args.delivery_json).strip():
        delivery_path = Path(args.delivery_json).expanduser().resolve()
        delivery = _load_json(delivery_path, label="delivery metadata")

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(work_code)
        revision = ledger.get_revision(revision_id)
        if revision["work_id"] != work["work_id"]:
            raise RuntimeError(f"revision {revision_id} does not belong to work {work_code}")

        cycle = ReviewCycle(workspace)
        result = apply_review_finding(
            cycle,
            ledger,
            revision_id,
            receipt,
            allowed_parameter_keys=request.get("allowed_parameter_keys") or [],
            current_parameters=request.get("current_parameters") or {},
        )

        accepted_revision_id = ""
        delivered_revision_id = ""
        if result["verdict"] == "PASS":
            accepted = ledger.accept_revision(revision_id)
            accepted_revision_id = accepted["revision_id"]
            status = "ACCEPTED"
            if delivery is not None:
                delivered = ledger.deliver_revision(revision_id, delivery=delivery)
                delivered_revision_id = str(delivered.get("delivered_revision_id") or "")
                status = "DELIVERED"
        elif result["verdict"] == "TUNE":
            status = "TUNING_REQUIRED"
        else:
            status = "TOOL_GAP_REWORK_REQUIRED" if result.get("finding_type") == "TOOL_GAP" else "REWORK_REQUIRED"

        output = {
            "schema_version": "openworker-llm-review-apply/v1",
            "work_code": work_code,
            "reviewed_revision_id": revision_id,
            "verdict": original_verdict,
            "finding_type": result.get("finding_type", original_verdict),
            "status": status,
            "accepted_revision_id": accepted_revision_id,
            "delivered_revision_id": delivered_revision_id,
            "next_revision_id": result.get("next_revision_id", ""),
            "parameters": result.get("parameters", {}),
            "parameter_delta": result.get("parameter_delta", []),
            "gap_capability": result.get("gap_capability", ""),
            "owning_repo": result.get("owning_repo", ""),
            "verification_plan": result.get("verification_plan", []),
            "review_request": str(request_path),
            "review_receipt": str(receipt_path),
            "ledger": ledger.snapshot(work["work_id"]),
        }
        out = workspace / "acceptance" / "openworker-review" / f"llm-review-apply-{revision_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, default=str))
        return 0 if result["verdict"] == "PASS" else 4
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"OPENWORKER_LLM_REVIEW_APPLY_FAIL {exc}", file=sys.stderr)
        raise
