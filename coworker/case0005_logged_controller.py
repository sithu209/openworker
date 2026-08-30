"""Case 0005 local controller with append-only durable supervisor ledger.

This module is deliberately Case-scoped so the stronger audit contract can be
validated on Case 0005 before being promoted to the generic controller.
Business execution stays on the resident OpenWorker node; GitHub is not a
business execution authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping

from .case0005_controller import Case0005Controller
from .case_worklist import CaseWorklistError

_LEDGER = "case-supervisor-ledger.jsonl"
_LEDGER_LOCK = "case-supervisor-ledger.lock"


class LoggedCase0005Controller(Case0005Controller):
    @property
    def ledger_path(self) -> Path:
        return self.workspace / ".openworker" / _LEDGER

    @property
    def ledger_lock_path(self) -> Path:
        return self.workspace / ".openworker" / _LEDGER_LOCK

    def _append_ledger(self, event_type: str, **fields: Any) -> None:
        path = self.ledger_path
        lock = self.ledger_lock_path
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 30.0
        fd: int | None = None
        while True:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 180:
                        lock.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise CaseWorklistError(f"supervisor ledger lock timeout: {lock}")
                time.sleep(0.05)
        try:
            if fd is not None:
                os.write(fd, (json.dumps({"pid": os.getpid(), "created_unix": time.time()}) + "\n").encode("utf-8"))
                os.close(fd)
                fd = None
            payload = {
                "schema": "openworker.case-supervisor-ledger/v1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "case_id": "0005",
                "machine": os.environ.get("COMPUTERNAME", ""),
                "pid": os.getpid(),
                "event_type": event_type,
                "workspace_root": str(self.workspace),
                **fields,
            }
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            if fd is not None:
                os.close(fd)
            lock.unlink(missing_ok=True)

    def bootstrap(self, manifest_path: str | Path, spec_path: str | Path) -> dict[str, Any]:
        self._append_ledger("bootstrap_start", manifest_path=str(manifest_path), spec_path=str(spec_path))
        try:
            result = super().bootstrap(manifest_path, spec_path)
        except Exception as exc:
            self._append_ledger("bootstrap_failed", error=str(exc))
            raise
        self._append_ledger("bootstrap_completed", result=result)
        return result

    def dispatch_ready(self) -> dict[str, Any]:
        try:
            worklist = self.runtime.load()
            snapshot = {
                "revision": worklist.revision,
                "ready_step_ids": [s.step_id for s in worklist.ready_steps()],
                "running_step_ids": [s.step_id for s in worklist.running_steps()],
                "max_local_slots": int(worklist.parallel_policy.get("max_local_slots", 4) or 4),
            }
            self._append_ledger("dispatch_scan", **snapshot)
        except Exception as exc:
            self._append_ledger("dispatch_scan_failed", error=str(exc))
            raise
        result = super().dispatch_ready()
        self._append_ledger("dispatch_result", result=result)
        return result

    def _dispatch_step(self, worklist, step, spec):
        action = step.allowed_actions[0] if len(step.allowed_actions) == 1 else ""
        self._append_ledger(
            "step_dispatch_start",
            step_id=step.step_id,
            action_id=action,
            worklist_revision=worklist.revision,
            step_kind=step.kind,
        )
        try:
            result = super()._dispatch_step(worklist, step, spec)
        except Exception as exc:
            self._append_ledger(
                "step_dispatch_failed",
                step_id=step.step_id,
                action_id=action,
                error=str(exc),
            )
            raise
        self._append_ledger(
            "step_durable_accepted",
            step_id=step.step_id,
            action_id=str(result.get("action_id", action)),
            execution_id=str(result.get("execution_id", "")),
            job_id=str(result.get("execution_id", "")),
            durable_ack=result.get("durable_ack"),
            dispatch_result=result,
        )
        return result

    def _job_payload(self, worklist, step, action: str, execution_id: str, claim_path: Path) -> dict[str, Any]:
        python = sys.executable or "python"
        argv = [
            python, "-m", "coworker.case0005_logged_controller", "run-step",
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

    def _video_child_payload(
        self,
        *,
        worklist,
        group_id: str,
        child_id: str,
        shot_id: str,
        claim_path: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        python = sys.executable or "python"
        argv = [
            python,
            "-m",
            "coworker.case0005_logged_controller",
            "run-video-shot",
            "--workspace",
            str(self.workspace),
            "--group-execution-id",
            group_id,
            "--child-job-id",
            child_id,
            "--shot-id",
            shot_id,
            "--claim",
            str(claim_path),
            "--fanout-manifest",
            str(manifest_path),
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

    def run_step(self, *, step_id: str, action_id: str, execution_id: str, claim_path: str | Path) -> dict[str, Any]:
        job_state = None
        try:
            job_state = self.node.job_status(execution_id)
        except Exception as exc:
            job_state = {"query_error": str(exc)}
        self._append_ledger(
            "step_job_running",
            step_id=step_id,
            action_id=action_id,
            execution_id=execution_id,
            job_id=execution_id,
            claim_path=str(claim_path),
            openworker_job=job_state,
        )
        try:
            result = super().run_step(
                step_id=step_id,
                action_id=action_id,
                execution_id=execution_id,
                claim_path=claim_path,
            )
        except Exception as exc:
            terminal = None
            try:
                terminal = self.node.job_status(execution_id)
            except Exception as status_exc:
                terminal = {"query_error": str(status_exc)}
            self._append_ledger(
                "step_failed",
                step_id=step_id,
                action_id=action_id,
                execution_id=execution_id,
                job_id=execution_id,
                error=str(exc),
                openworker_job=terminal,
            )
            raise
        terminal = None
        try:
            terminal = self.node.job_status(execution_id)
        except Exception as exc:
            terminal = {"query_error": str(exc)}
        self._append_ledger(
            "step_passed",
            step_id=step_id,
            action_id=action_id,
            execution_id=execution_id,
            job_id=execution_id,
            evidence=result.get("evidence"),
            downstream=result.get("downstream"),
            openworker_job=terminal,
        )
        return result

    def run_video_shot(self, **kwargs: Any) -> dict[str, Any]:
        child_id = str(kwargs.get("child_job_id", ""))
        shot_id = str(kwargs.get("shot_id", ""))
        self._append_ledger(
            "video_child_running",
            step_id="0005-060",
            action_id="comfyx.production.video.real",
            execution_id=child_id,
            job_id=child_id,
            shot_id=shot_id,
        )
        try:
            result = super().run_video_shot(**kwargs)
        except Exception as exc:
            self._append_ledger(
                "video_child_failed",
                step_id="0005-060",
                action_id="comfyx.production.video.real",
                execution_id=child_id,
                job_id=child_id,
                shot_id=shot_id,
                error=str(exc),
            )
            raise
        self._append_ledger(
            "video_child_passed",
            step_id="0005-060",
            action_id="comfyx.production.video.real",
            execution_id=child_id,
            job_id=child_id,
            shot_id=shot_id,
            result=result,
        )
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Case 0005 logged local controller")
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
    controller = LoggedCase0005Controller(args.workspace, node_url=args.node_url, spec_path=getattr(args, "spec", None))
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
            controller._append_ledger("controller_command_failed", command=args.command, error=str(exc))
        except Exception:
            pass
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.command not in {"run-step", "run-video-shot"}:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
