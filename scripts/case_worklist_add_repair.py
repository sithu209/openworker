from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklistError
from coworker.case_worklist_runtime import CaseWorklistRuntime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--parent-step", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--allowed-action", action="append", required=True)
    parser.add_argument("--acceptance", action="append", default=[])
    args = parser.parse_args()

    runtime = CaseWorklistRuntime(args.workspace_root)
    with runtime.lock():
        worklist = runtime.store.load()
        try:
            repair = worklist.step(args.step_id)
        except CaseWorklistError:
            repair = worklist.add_repair(
                parent_step_id=args.parent_step,
                step_id=args.step_id,
                title=args.title,
                allowed_actions=args.allowed_action,
                acceptance=args.acceptance,
            )
            runtime.store.save(worklist)
        else:
            if repair.kind != "repair" or repair.repair_parent_step != args.parent_step:
                raise CaseWorklistError(f"existing step {args.step_id!r} is not the requested repair")

    print(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2))
    print(f"CASE_WORKLIST_REPAIR_READY step={args.step_id} parent={args.parent_step}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE_WORKLIST_REPAIR_FAIL: {exc}")
        raise SystemExit(2)
