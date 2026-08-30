"""OpenWorker-native Case 0005 controller.

This wrapper keeps OpenWorker :8787 as the durable scheduler/supervisor and
uses the existing verified Case 0005 business mappings. It deliberately does
not use go-tool :8848 as supervisor health or fanout queue authority.

The legacy capability executor used by ``_execute_local_claim`` is still a
separate migration item; this module fixes Case admission, durable visibility,
and scheduling authority first.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .case0005_controller import Case0005Controller
from .case0005_true_local_controller import TrueLocalCase0005Controller
from .case0005_verified_local_controller import VerifiedLocalCase0005Controller
from .case_worklist import CaseWorklistError


class OpenWorkerNativeCase0005Controller(VerifiedLocalCase0005Controller):
    def _require_verified_local_supervisor(self, operation: str) -> dict:
        status = self.node.node_status()
        machine = str(status.get("machine", "")).strip()
        worklist = self.runtime.load()
        expected = str(worklist.assigned_host).strip()
        online = bool(status.get("online", True))
        max_workers = int(status.get("max_workers", 0) or 0)
        if machine.lower() != expected.lower():
            raise CaseWorklistError(
                f"OpenWorker supervisor machine mismatch expected={expected} actual={machine}"
            )
        if not online:
            raise CaseWorklistError("OpenWorker supervisor is offline")
        if max_workers < 4:
            raise CaseWorklistError(
                f"OpenWorker supervisor max_workers={max_workers}, expected >=4"
            )
        self._append_ledger(
            "openworker_native_supervisor_check_passed",
            operation=operation,
            supervisor_url=self.node.base_url,
            supervisor_machine=machine,
            max_workers=max_workers,
            authority="openworker-local-supervisor",
            github_action_used_for_business_execution=False,
        )
        return status

    # Bypass the later direct-queue mixin that moved fanout children to :8848.
    # The earlier TrueLocal/Case0005 implementations already submit native
    # OpenWorker :8787 jobs with one durable child per asset/shot.
    def _dispatch_image_fanout(self, worklist, step, action: str, role: str) -> dict[str, Any]:
        return TrueLocalCase0005Controller._dispatch_image_fanout(
            self, worklist, step, action, role
        )

    def _dispatch_video_fanout(self, worklist, step, action: str) -> dict[str, Any]:
        return Case0005Controller._dispatch_video_fanout(self, worklist, step, action)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Case 0005 OpenWorker-native controller")
    parser.add_argument("--node-url", default="http://127.0.0.1:8787")
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--workspace", required=True)
    bootstrap.add_argument("--manifest", required=True)
    bootstrap.add_argument("--spec", required=True)
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--workspace", required=True)
    dispatch.add_argument("--spec")
    run = sub.add_parser("run-step")
    run.add_argument("--workspace", required=True)
    run.add_argument("--spec")
    run.add_argument("--step-id", required=True)
    run.add_argument("--action-id", required=True)
    run.add_argument("--execution-id", required=True)
    run.add_argument("--claim", required=True)
    image = sub.add_parser("run-image-asset")
    image.add_argument("--workspace", required=True)
    image.add_argument("--step-id", required=True)
    image.add_argument("--group-execution-id", required=True)
    image.add_argument("--child-job-id", required=True)
    image.add_argument("--asset-id", required=True)
    image.add_argument("--role", required=True)
    image.add_argument("--claim", required=True)
    image.add_argument("--fanout-manifest", required=True)
    video = sub.add_parser("run-video-shot")
    video.add_argument("--workspace", required=True)
    video.add_argument("--spec")
    video.add_argument("--group-execution-id", required=True)
    video.add_argument("--child-job-id", required=True)
    video.add_argument("--shot-id", required=True)
    video.add_argument("--claim", required=True)
    video.add_argument("--fanout-manifest", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    controller = OpenWorkerNativeCase0005Controller(
        args.workspace,
        node_url=args.node_url,
        spec_path=getattr(args, "spec", None),
    )
    try:
        if args.command == "bootstrap":
            result = controller.bootstrap(args.manifest, args.spec)
        elif args.command == "dispatch":
            result = controller.dispatch_ready()
        elif args.command == "run-step":
            result = controller.run_step(
                step_id=args.step_id,
                action_id=args.action_id,
                execution_id=args.execution_id,
                claim_path=args.claim,
            )
        elif args.command == "run-image-asset":
            result = controller.run_image_asset(
                step_id=args.step_id,
                group_execution_id=args.group_execution_id,
                child_job_id=args.child_job_id,
                asset_id=args.asset_id,
                role=args.role,
                claim_path=args.claim,
                fanout_manifest=args.fanout_manifest,
            )
        else:
            result = controller.run_video_shot(
                group_execution_id=args.group_execution_id,
                child_job_id=args.child_job_id,
                shot_id=args.shot_id,
                claim_path=args.claim,
                fanout_manifest=args.fanout_manifest,
            )
    except Exception as exc:
        try:
            controller._append_ledger(
                "openworker_native_controller_command_failed",
                command=args.command,
                error=str(exc),
            )
        except Exception:
            pass
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.command not in {"run-step", "run-image-asset", "run-video-shot"}:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
