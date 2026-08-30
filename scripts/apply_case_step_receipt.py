from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklistStore, CaseWorklistError
from coworker.case_worklist_runtime import CaseWorklistRuntime


def _scalar(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace-root", required=True)
    p.add_argument("--step-id", required=True)
    p.add_argument("--action-id", required=True)
    p.add_argument("--execution-id", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--expected-run-id")
    args = p.parse_args()

    workspace = Path(args.workspace_root).resolve()
    receipt_path = Path(args.receipt).resolve()
    try:
        receipt_path.relative_to(workspace)
    except ValueError as exc:
        raise CaseWorklistError(f"receipt escapes workspace: {receipt_path}") from exc
    if not receipt_path.is_file() or receipt_path.stat().st_size <= 0:
        raise CaseWorklistError(f"receipt missing/empty: {receipt_path}")

    raw = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise CaseWorklistError("receipt root must be object")

    runtime = CaseWorklistRuntime(workspace)
    worklist = runtime.load()
    step = next((s for s in worklist.steps if s.step_id == args.step_id), None)
    if step is None:
        raise CaseWorklistError(f"step not found: {args.step_id}")
    if args.action_id not in step.allowed_actions:
        raise CaseWorklistError(f"action {args.action_id} not allowed for {args.step_id}")

    if args.expected_run_id is not None:
        actual = str(raw.get("run_id", "")).strip()
        if actual != str(args.expected_run_id).strip():
            raise CaseWorklistError(f"run_id mismatch expected={args.expected_run_id} actual={actual}")

    missing = [key for key in step.acceptance if key not in raw]
    if missing:
        raise CaseWorklistError(f"receipt missing acceptance keys: {missing}")

    for key in step.acceptance:
        runtime.record(args.step_id, key, _scalar(raw[key]))
    runtime.record(args.step_id, "governed_receipt", str(receipt_path))
    runtime.complete_action(args.step_id, args.action_id, execution_id=args.execution_id)
    accepted = runtime.pass_step(args.step_id)
    print(json.dumps(accepted.as_dict(), ensure_ascii=False, indent=2))
    print(f"CASE_STEP_RECEIPT_ACCEPTED step={args.step_id} next={accepted.as_dict()['canonical_next_step_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
