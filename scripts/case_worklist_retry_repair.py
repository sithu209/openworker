from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklistError, StepStatus
from coworker.case_worklist_runtime import CaseWorklistRuntime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    runtime = CaseWorklistRuntime(args.workspace_root)
    with runtime.lock():
        worklist = runtime.store.load()
        step = worklist.step(args.step_id)
        if step.kind != "repair":
            raise CaseWorklistError("only repair steps may be retried")
        if step.status == StepStatus.BLOCKED:
            step.status = StepStatus.PENDING
            step.blocker = ""
            step.evidence.pop("__openworker_active_action", None)
            step.evidence.pop("__openworker_active_execution", None)
            step.evidence["repair_retry_reason"] = args.reason.strip()
            worklist.revision += 1
            worklist.refresh()
            runtime.store.save(worklist)
        elif step.status not in {StepStatus.READY, StepStatus.PENDING}:
            raise CaseWorklistError(f"repair step cannot be retried from {step.status.value}")

    print(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2))
    print(f"CASE_WORKLIST_REPAIR_RETRY_READY step={args.step_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE_WORKLIST_REPAIR_RETRY_FAIL: {exc}")
        raise SystemExit(2)
