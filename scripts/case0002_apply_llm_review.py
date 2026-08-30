"""Apply a ChatGPT Drive review receipt to Case 0002 Aladdin WorkLedger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from coworker.review_cycle import ReviewCycle
from coworker.review_gap import apply_review_finding
from coworker.work_ledger import WorkLedger

from scripts.case0002_review_handoff import WORK_CODE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    if not receipt_path.is_file() or receipt_path.stat().st_size <= 0:
        raise RuntimeError(f"review receipt unavailable: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    revision_id = str(args.revision_id).strip()

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(WORK_CODE)
        revision = ledger.get_revision(revision_id)
        if revision["work_id"] != work["work_id"]:
            raise RuntimeError("revision does not belong to Case 0002 work")
        request_path = workspace / ".openworker" / "reviews" / revision_id / "review-request.json"
        if not request_path.is_file():
            raise RuntimeError(f"review request unavailable: {request_path}")
        request = json.loads(request_path.read_text(encoding="utf-8"))

        cycle = ReviewCycle(workspace)
        result = apply_review_finding(
            cycle,
            ledger,
            revision_id,
            receipt,
            allowed_parameter_keys=request.get("allowed_parameter_keys") or [],
            current_parameters=request.get("current_parameters") or {},
        )

        if result["verdict"] == "PASS":
            accepted = ledger.accept_revision(revision_id)
            delivered = ledger.deliver_revision(
                revision_id,
                delivery={
                    "case_id": "0002",
                    "review_receipt": str(receipt_path),
                    "reviewed_artifact_bundle": str(request_path.parent),
                },
            )
            status = "DELIVERED"
            accepted_revision_id = accepted["revision_id"]
            delivered_revision_id = delivered["delivered_revision_id"]
        elif result["verdict"] == "TUNE":
            status = "TUNING_REQUIRED"
            accepted_revision_id = ""
            delivered_revision_id = ""
        else:
            status = "TOOL_GAP_REWORK_REQUIRED" if result.get("finding_type") == "TOOL_GAP" else "REWORK_REQUIRED"
            accepted_revision_id = ""
            delivered_revision_id = ""

        output = {
            "schema_version": "openworker-case0002-llm-review-apply/v1",
            "case_id": "0002",
            "reviewed_revision_id": revision_id,
            "verdict": str(receipt.get("verdict") or "").strip().upper(),
            "finding_type": result.get("finding_type", result["verdict"]),
            "status": status,
            "accepted_revision_id": accepted_revision_id,
            "delivered_revision_id": delivered_revision_id,
            "next_revision_id": result.get("next_revision_id", ""),
            "parameters": result.get("parameters", {}),
            "parameter_delta": result.get("parameter_delta", []),
            "gap_capability": result.get("gap_capability", ""),
            "owning_repo": result.get("owning_repo", ""),
            "verification_plan": result.get("verification_plan", []),
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
        print(f"CASE0002_LLM_REVIEW_APPLY_FAIL {exc}", file=sys.stderr)
        raise
