"""Stable authority entrypoint for Case 0005 true local supervision.

All child controller processes re-enter this exact module. This prevents an
inherited payload builder from silently downgrading orchestration back to an
older controller class after a step completes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from .case0005_true_local_controller import TrueLocalCase0005Controller

_MODULE = "coworker.case0005_local_supervisor"


class Case0005LocalSupervisor(TrueLocalCase0005Controller):
    def _job_payload(self, worklist, step, action: str, execution_id: str, claim_path: Path) -> dict[str, Any]:
        argv = [
            sys.executable or "python", "-m", _MODULE, "run-step",
            "--workspace", str(self.workspace),
            "--step-id", step.step_id,
            "--action-id", action,
            "--execution-id", execution_id,
            "--claim", str(claim_path),
        ]
        return {
            "job_id": execution_id,
            "dispatch_id": "local-controller-" + execution_id,
            "machine": worklist.assigned_host,
            "priority": 100 if step.kind in {"fanout", "join"} else 80,
            "command": subprocess.list2cmdline(argv),
            "cwd": str(self.openworker_root),
            "workspace_root": str(self.workspace),
            "env": self._localexec_env(),
            "timeout_sec": 3600,
            "locks": [f"case:{worklist.case_id}:step:{step.step_id}"],
        }

    def _image_child_payload(
        self, *, worklist, step_id: str, group_id: str, child_id: str,
        asset_id: str, role: str, claim_path: Path, manifest_path: Path,
    ) -> dict[str, Any]:
        argv = [
            sys.executable or "python", "-m", _MODULE, "run-image-asset",
            "--workspace", str(self.workspace),
            "--step-id", step_id,
            "--group-execution-id", group_id,
            "--child-job-id", child_id,
            "--asset-id", asset_id,
            "--role", role,
            "--claim", str(claim_path),
            "--fanout-manifest", str(manifest_path),
        ]
        return {
            "job_id": child_id,
            "dispatch_id": "local-controller-" + child_id,
            "machine": worklist.assigned_host,
            "priority": 100,
            "command": subprocess.list2cmdline(argv),
            "cwd": str(self.openworker_root),
            "workspace_root": str(self.workspace),
            "env": self._localexec_env(),
            "timeout_sec": 2100,
            "locks": [f"case:{worklist.case_id}:image-asset:{self._safe_id(asset_id)}"],
        }

    def _video_child_payload(
        self, *, worklist, group_id: str, child_id: str, shot_id: str,
        claim_path: Path, manifest_path: Path,
    ) -> dict[str, Any]:
        argv = [
            sys.executable or "python", "-m", _MODULE, "run-video-shot",
            "--workspace", str(self.workspace),
            "--group-execution-id", group_id,
            "--child-job-id", child_id,
            "--shot-id", shot_id,
            "--claim", str(claim_path),
            "--fanout-manifest", str(manifest_path),
        ]
        return {
            "job_id": child_id,
            "dispatch_id": "local-controller-" + child_id,
            "machine": worklist.assigned_host,
            "priority": 100,
            "command": subprocess.list2cmdline(argv),
            "cwd": str(self.openworker_root),
            "workspace_root": str(self.workspace),
            "env": self._localexec_env(),
            "timeout_sec": 2100,
            "locks": [f"case:{worklist.case_id}:video-shot:{self._safe_id(shot_id)}"],
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Case 0005 stable true-local supervisor authority")
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
    image.add_argument("--spec")
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
    controller = Case0005LocalSupervisor(
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
                "controller_command_failed",
                command=args.command,
                controller_module=_MODULE,
                execution_route="local_supervisor",
                error=str(exc),
            )
        except Exception:
            pass
        print(json.dumps({"status":"failed","error":str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.command not in {"run-step", "run-image-asset", "run-video-shot"}:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
