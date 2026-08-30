"""CLI control/query surface for the OpenWorker Git-like work ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

from .work_ledger import WorkLedger, WorkLedgerError


def _json_arg(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("JSON value must be an object")
    return value


def _ledger_path(workspace: str, db: str | None) -> Path:
    if db:
        return Path(db).expanduser().resolve()
    root = Path(workspace).expanduser().resolve()
    return root / ".openworker" / "work-ledger.sqlite"


def _resolve_work(ledger: WorkLedger, value: str) -> dict[str, Any]:
    if value.startswith("wrk_"):
        return ledger.get_work(value)
    return ledger.get_work_by_code(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openworker-work-ledger",
        description="Track OpenWorker work as immutable Git-like revisions, acceptance and rework.",
    )
    parser.add_argument("--workspace", default=".", help="work workspace; ledger defaults to .openworker/work-ledger.sqlite")
    parser.add_argument("--db", help="explicit ledger SQLite path")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a work and initial revision")
    init.add_argument("--code", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--goal", default="")
    init.add_argument("--plan-json")

    show = sub.add_parser("show", help="show the complete work snapshot/history")
    show.add_argument("--work", required=True, help="work_id or code")

    revision = sub.add_parser("revision", help="open a child revision")
    revision.add_argument("--work", required=True)
    revision.add_argument("--kind", default="progress")
    revision.add_argument("--goal", default="")
    revision.add_argument("--plan-json")
    revision.add_argument("--reason", default="")
    revision.add_argument("--gap-owner-repo", default="")

    check = sub.add_parser("check", help="record/update a revision acceptance check")
    check.add_argument("--revision", required=True)
    check.add_argument("--name", required=True)
    check.add_argument("--status", required=True)
    check.add_argument("--optional", action="store_true")
    check.add_argument("--evidence-json")
    check.add_argument("--reason", default="")

    artifact = sub.add_parser("artifact", help="record a physical artifact with computed SHA256")
    artifact.add_argument("--revision", required=True)
    artifact.add_argument("--name", required=True)
    artifact.add_argument("--path", required=True)
    artifact.add_argument("--provenance-json")

    rework = sub.add_parser("rework", help="mark a revision REWORK_REQUIRED and open a child rework revision")
    rework.add_argument("--revision", required=True)
    rework.add_argument("--reason", required=True)
    rework.add_argument("--gap-owner-repo", default="")
    rework.add_argument("--goal", default="")
    rework.add_argument("--plan-json")

    accept = sub.add_parser("accept", help="run fail-closed acceptance gate and move accepted pointer")
    accept.add_argument("--revision", required=True)

    deliver = sub.add_parser("deliver", help="deliver an accepted revision")
    deliver.add_argument("--revision", required=True)
    deliver.add_argument("--delivery-json")

    rollback = sub.add_parser("rollback-head", help="move HEAD to last accepted revision without deleting history")
    rollback.add_argument("--work", required=True)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = _ledger_path(args.workspace, args.db)
    ledger = WorkLedger(db_path)
    try:
        if args.command == "init":
            result = ledger.create_work(
                code=args.code,
                title=args.title,
                workspace=str(Path(args.workspace).expanduser().resolve()),
                goal=args.goal,
                plan=_json_arg(args.plan_json),
            )
        elif args.command == "show":
            work = _resolve_work(ledger, args.work)
            result = ledger.snapshot(work["work_id"])
        elif args.command == "revision":
            work = _resolve_work(ledger, args.work)
            result = ledger.open_revision(
                work["work_id"],
                kind=args.kind,
                goal=args.goal,
                plan=_json_arg(args.plan_json),
                reason=args.reason,
                gap_owner_repo=args.gap_owner_repo,
            )
        elif args.command == "check":
            result = ledger.set_check(
                args.revision,
                name=args.name,
                status=args.status,
                required=not args.optional,
                evidence=_json_arg(args.evidence_json),
                reason=args.reason,
            )
        elif args.command == "artifact":
            result = ledger.add_file_artifact(
                args.revision,
                logical_name=args.name,
                path=args.path,
                provenance=_json_arg(args.provenance_json),
            )
        elif args.command == "rework":
            ledger.request_rework(
                args.revision,
                reason=args.reason,
                gap_owner_repo=args.gap_owner_repo,
            )
            result = ledger.open_rework(
                args.revision,
                goal=args.goal,
                plan=_json_arg(args.plan_json),
                reason=args.reason,
                gap_owner_repo=args.gap_owner_repo,
            )
        elif args.command == "accept":
            result = ledger.accept_revision(args.revision)
        elif args.command == "deliver":
            result = ledger.deliver_revision(args.revision, delivery=_json_arg(args.delivery_json))
        elif args.command == "rollback-head":
            work = _resolve_work(ledger, args.work)
            result = ledger.move_head_to_accepted(work["work_id"])
        else:  # pragma: no cover
            parser.error(f"unknown command: {args.command}")
            return
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    except (WorkLedgerError, json.JSONDecodeError) as exc:
        parser.exit(2, f"WORK_LEDGER_ERROR: {exc}\n")
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
