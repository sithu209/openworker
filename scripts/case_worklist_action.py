from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklist, CaseWorklistError, CaseWorklistStore
from coworker.case_worklist_runtime import CaseWorklistRuntime


def load_manifest(path: Path) -> CaseWorklist:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise CaseWorklistError("worklist manifest root must be an object")
    return CaseWorklist.from_dict(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["ensure", "show", "add-repair", "start", "complete-action", "retry-stale-active", "record", "pass", "block-active"],
    )
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--step-id")
    parser.add_argument("--parent-step-id")
    parser.add_argument("--title")
    parser.add_argument("--allowed-action", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    parser.add_argument("--action-id")
    parser.add_argument("--execution-id")
    parser.add_argument("--key")
    parser.add_argument("--value")
    parser.add_argument("--reason")
    args = parser.parse_args()

    runtime = CaseWorklistRuntime(args.workspace_root)
    store = CaseWorklistStore(args.workspace_root)

    if args.command == "ensure":
        manifest = None
        if args.manifest:
            manifest = load_manifest(Path(args.manifest).resolve())
            if Path(manifest.workspace_root).resolve() != Path(args.workspace_root).resolve():
                raise CaseWorklistError("manifest workspace_root does not match --workspace-root")
        worklist = runtime.ensure(manifest)
        print(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2))
        print(f"CASE_WORKLIST_READY path={store.path} next={worklist.as_dict()['canonical_next_step_id']}")
        return 0

    if args.command == "show":
        worklist = runtime.load()
        print(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2))
        return 0

    if not args.step_id:
        raise CaseWorklistError("--step-id is required")

    if args.command == "add-repair":
        if not args.parent_step_id:
            raise CaseWorklistError("--parent-step-id is required for add-repair")
        if not args.title:
            raise CaseWorklistError("--title is required for add-repair")
        if not args.allowed_action:
            raise CaseWorklistError("at least one --allowed-action is required for add-repair")
        worklist = runtime.add_repair(parent_step_id=args.parent_step_id, step_id=args.step_id, title=args.title, allowed_actions=args.allowed_action, acceptance=args.acceptance)
    elif args.command == "start":
        if not args.action_id:
            raise CaseWorklistError("--action-id is required for start")
        if not args.execution_id:
            raise CaseWorklistError("--execution-id is required for start")
        worklist = runtime.start_action(args.step_id, args.action_id, execution_id=args.execution_id)
    elif args.command == "complete-action":
        if not args.action_id:
            raise CaseWorklistError("--action-id is required for complete-action")
        if not args.execution_id:
            raise CaseWorklistError("--execution-id is required for complete-action")
        worklist = runtime.complete_action(args.step_id, args.action_id, execution_id=args.execution_id)
    elif args.command == "retry-stale-active":
        if not args.execution_id:
            raise CaseWorklistError("--execution-id is required for retry-stale-active")
        worklist = runtime.retry_stale_active(args.step_id, execution_id=args.execution_id)
    elif args.command == "record":
        if not args.key:
            raise CaseWorklistError("--key is required for record")
        if args.value is None:
            raise CaseWorklistError("--value is required for record")
        worklist = runtime.record(args.step_id, args.key, args.value)
    elif args.command == "pass":
        worklist = runtime.pass_step(args.step_id)
    elif args.command == "block-active":
        if not args.reason:
            raise CaseWorklistError("--reason is required for block-active")
        worklist = runtime.block_active(args.step_id, args.reason)
    else:
        raise CaseWorklistError(f"unsupported command: {args.command}")

    print(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2))
    print(f"CASE_WORKLIST_UPDATED command={args.command} step={args.step_id} next={worklist.as_dict()['canonical_next_step_id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE_WORKLIST_FAIL: {exc}")
        raise SystemExit(2)
