from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklistError, CaseWorklistStore, StepStatus


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace-root", required=True)
    p.add_argument("--step-id", required=True)
    p.add_argument("--expected-blocker", required=True)
    args = p.parse_args()

    store = CaseWorklistStore(args.workspace_root)
    worklist = store.load()
    step = worklist.step(args.step_id)
    expected = args.expected_blocker.strip()
    if not expected:
        raise CaseWorklistError("--expected-blocker must be non-empty")
    if step.status != StepStatus.BLOCKED:
        raise CaseWorklistError(f"blocked retry requires BLOCKED step, got {step.status.value}")
    if step.blocker.strip() != expected:
        raise CaseWorklistError(
            f"blocked retry reason mismatch expected={expected!r} actual={step.blocker!r}"
        )
    if step.evidence.get("__openworker_active_action") or step.evidence.get("__openworker_active_execution"):
        raise CaseWorklistError("blocked retry refuses step with active execution evidence")

    step.status = StepStatus.READY
    step.blocker = ""
    worklist.revision += 1
    worklist.refresh()
    store.save(worklist)
    print(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2))
    print(f"CASE_BLOCKED_STEP_RETRY_OK step={step.step_id} next={worklist.as_dict()['canonical_next_step_id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE_BLOCKED_STEP_RETRY_FAIL: {exc}")
        raise SystemExit(2)
