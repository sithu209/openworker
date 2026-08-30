"""Event-driven local CaseWorklist controller.

This is business orchestration, not a process scheduler.  The controller reads
OpenWorker's durable CaseWorklist, builds go-tool localexec claims, and submits
child jobs to the local Go execution kernel.  PID/slot/heartbeat/timeout/cancel
remain exclusively owned by the Go node.

Normal case transitions never require GitHub Actions.  One external transport
may bootstrap/kick the local controller when ChatGPT cannot reach the machine,
but every business child job is then accepted and executed locally.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping

from .case_worklist import CaseStep, CaseWorklist, CaseWorklistError, StepStatus
from .case_worklist_runtime import CaseWorklistRuntime
from .node_client import OpenWorkerNodeClient

_ACTIVE_ACTION_KEY = "__openworker_active_action"
_ACTIVE_EXECUTION_KEY = "__openworker_active_execution"
_SPEC_NAME = "case-spec.json"
_CONTROLLER_RECEIPT = "case-controller-last.json"


class LocalCaseController:
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        node_url: str = "http://127.0.0.1:8787",
        spec_path: str | Path | None = None,
    ) -> None:
        self.workspace = Path(workspace_root).expanduser().resolve()
        self.runtime = CaseWorklistRuntime(self.workspace)
        self.node = OpenWorkerNodeClient(node_url)
        self.openworker_root = Path(__file__).resolve().parents[1]
        self.spec_path = Path(spec_path).expanduser().resolve() if spec_path else self.workspace / ".openworker" / _SPEC_NAME

    def bootstrap(self, manifest_path: str | Path, spec_path: str | Path) -> dict[str, Any]:
        self.workspace.mkdir(parents=True, exist_ok=True)
        raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if str(raw.get("workspace_root", "")).strip() != str(self.workspace):
            raw["workspace_root"] = str(self.workspace)
        manifest = CaseWorklist.from_dict(raw)
        self.runtime.ensure(manifest)
        spec = self._load_json(Path(spec_path))
        if str(spec.get("case_id", "")).strip() != manifest.case_id:
            raise CaseWorklistError("case spec case_id does not match Worklist")
        persisted_spec = self.workspace / ".openworker" / _SPEC_NAME
        persisted_spec.parent.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(persisted_spec, spec)
        self.spec_path = persisted_spec
        return self.dispatch_ready()

    def dispatch_ready(self) -> dict[str, Any]:
        worklist = self.runtime.load()
        self._assert_local_node(worklist)
        spec = self._load_spec(worklist.case_id)
        ready = worklist.ready_steps()
        dispatched: list[dict[str, Any]] = []
        attention: list[dict[str, Any]] = []
        for step in ready:
            if step.kind == "approval":
                attention.append({"step_id": step.step_id, "reason": "user_approval_required", "title": step.title})
                continue
            try:
                item = self._dispatch_step(worklist, step, spec)
            except NotImplementedError as exc:
                attention.append({"step_id": step.step_id, "reason": "controller_expansion_required", "detail": str(exc)})
                continue
            dispatched.append(item)
        result = {
            "schema_version": "openworker-local-case-controller/v1",
            "case_id": worklist.case_id,
            "machine": worklist.assigned_host,
            "workspace_root": str(self.workspace),
            "ready_step_ids": [step.step_id for step in ready],
            "running_step_ids": [step.step_id for step in self.runtime.load().running_steps()],
            "dispatched": dispatched,
            "attention": attention,
            "github_action_used_for_business_execution": False,
        }
        self._write_controller_receipt(result)
        return result

    def run_step(self, *, step_id: str, action_id: str, execution_id: str, claim_path: str | Path) -> dict[str, Any]:
        worklist = self.runtime.load()
        step = worklist.step(step_id)
        active_action = str(step.evidence.get(_ACTIVE_ACTION_KEY, "") or "").strip()
        active_execution = str(step.evidence.get(_ACTIVE_EXECUTION_KEY, "") or "").strip()
        if active_action != action_id or active_execution != execution_id:
            raise CaseWorklistError(
                f"local step ownership mismatch: step={step_id} action={active_action!r} execution={active_execution!r}"
            )
        claim = self._load_json(Path(claim_path))
        if str(claim.get("work_id", "")) != execution_id or str(claim.get("capability_id", "")) != action_id:
            raise CaseWorklistError("claim identity does not match active Worklist execution")
        try:
            local_result = self._execute_local_claim(Path(claim_path))
            evidence = self._acceptance_evidence(step, local_result)
            self.runtime.accept_action_evidence(step_id, action_id, execution_id=execution_id, evidence=evidence)
        except Exception as exc:
            try:
                self.runtime.record(step_id, "localexec_error", str(exc))
            except Exception:
                pass
            self.runtime.block_active(step_id, f"localexec failed: {exc}")
            self._write_controller_receipt({
                "schema_version": "openworker-local-case-controller/v1",
                "case_id": worklist.case_id,
                "step_id": step_id,
                "execution_id": execution_id,
                "status": "blocked",
                "error": str(exc),
            })
            raise

        downstream: dict[str, Any] | None = None
        try:
            downstream = self.dispatch_ready()
        except Exception as exc:
            # Current step is already durably accepted.  A transient downstream
            # dispatch failure must not rewrite the successful business result;
            # the next supervisor/controller kick can deterministically resume.
            downstream = {"attention": [{"reason": "downstream_dispatch_failed", "detail": str(exc)}]}
        result = {
            "schema_version": "openworker-local-step-result/v1",
            "case_id": worklist.case_id,
            "step_id": step_id,
            "action_id": action_id,
            "execution_id": execution_id,
            "status": "passed",
            "evidence": evidence,
            "downstream": downstream,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return result

    def _dispatch_step(self, worklist: CaseWorklist, step: CaseStep, spec: Mapping[str, Any]) -> dict[str, Any]:
        if len(step.allowed_actions) != 1:
            raise NotImplementedError(
                f"step {step.step_id} has {len(step.allowed_actions)} actions; multi-action phase controller not materialized yet"
            )
        action = step.allowed_actions[0]
        inputs = self._claim_inputs(worklist, step, action, spec)
        revision = worklist.revision
        execution_id = self._execution_id(worklist.case_id, step.step_id, action, revision)
        claim_dir = self.workspace / ".openworker" / "claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim_path = claim_dir / f"{execution_id}.json"
        claim = {
            "work_id": execution_id,
            "assigned_host": worklist.assigned_host,
            "capability_id": action,
            "inputs": inputs,
            "claimed_by": "openworker-local-case-controller",
            "lease_token": execution_id,
        }
        self._write_json_atomic(claim_path, claim)

        # Start Worklist ownership before exposing the durable child job. If the
        # node submit fails synchronously, roll back exactly this execution.
        self.runtime.start_action(step.step_id, action, execution_id=execution_id)
        payload = self._job_payload(worklist, step, action, execution_id, claim_path)
        try:
            ack = self.node.submit(payload)
        except Exception:
            self.runtime.retry_stale_active(step.step_id, execution_id=execution_id)
            raise
        if not bool(ack.get("accepted")):
            self.runtime.retry_stale_active(step.step_id, execution_id=execution_id)
            raise CaseWorklistError(f"local OpenWorker did not durably accept {execution_id}")
        return {"step_id": step.step_id, "action_id": action, "execution_id": execution_id, "durable_ack": ack}

    def _job_payload(self, worklist: CaseWorklist, step: CaseStep, action: str, execution_id: str, claim_path: Path) -> dict[str, Any]:
        python = sys.executable or "python"
        argv = [
            python, "-m", "coworker.case_controller", "run-step",
            "--workspace", str(self.workspace),
            "--step-id", step.step_id,
            "--action-id", action,
            "--execution-id", execution_id,
            "--claim", str(claim_path),
        ]
        command = subprocess.list2cmdline(argv)
        env = self._localexec_env()
        return {
            "job_id": execution_id,
            "dispatch_id": "local-controller-" + execution_id,
            "machine": worklist.assigned_host,
            "priority": 100 if step.kind in {"fanout", "join"} else 80,
            "command": command,
            "cwd": str(self.openworker_root),
            "workspace_root": str(self.workspace),
            "env": env,
            "timeout_sec": 3600,
            "locks": [f"case:{worklist.case_id}:step:{step.step_id}"],
        }

    def _claim_inputs(self, worklist: CaseWorklist, step: CaseStep, action: str, spec: Mapping[str, Any]) -> dict[str, Any]:
        common = {"workspace_root": str(self.workspace), "assigned_host": worklist.assigned_host}
        if action == "comfyx-studio.director.preproduction":
            return {
                **common,
                "case_id": worklist.case_id,
                "source_title": str(spec.get("title", "")).strip(),
                "source_story": str(spec.get("source_story", "")).strip(),
            }
        if action == "comfyx-studio.storyboard.plan":
            return {**common, "director_plan_relpath": str(spec.get("director_plan_relpath", "director/project-plan.json"))}
        if action == "presentation.openmaic":
            if step.step_id.endswith("025"):
                cfg = self._mapping(spec, "text_storyboard")
            elif step.step_id.endswith("055"):
                cfg = self._mapping(spec, "illustrated_storyboard")
            else:
                raise NotImplementedError(f"presentation claim mapping is not defined for {step.step_id}")
            return {**common, "request_relpath": str(cfg.get("request_relpath", "")), "output_relpath": str(cfg.get("output_relpath", ""))}
        if action in {"image.comfyx.storyboard-real", "comfyx.production.video.real"}:
            raise NotImplementedError(
                f"{action} requires fan-out inputs derived from the REAL visual/video plan; controller will materialize this after upstream evidence exists"
            )
        if action == "comfyx-studio.finalize":
            parent = worklist.step("0005-060")
            videos = parent.evidence.get("shot_videos")
            if not isinstance(videos, list) or not videos:
                raise CaseWorklistError("finalize requires durable shot_videos evidence from fan-out")
            rels = [str(Path(str(p)).resolve().relative_to(self.workspace)) if Path(str(p)).is_absolute() else str(p) for p in videos]
            return {**common, "shot_video_relpaths": ",".join(rels), "subtitle_relpath": "", "output_relpath": "final/final.mp4"}
        raise NotImplementedError(f"local claim builder is not registered for {action}")

    def _acceptance_evidence(self, step: CaseStep, local_result: Mapping[str, Any]) -> dict[str, Any]:
        if str(local_result.get("status", "")).lower() != "completed":
            raise CaseWorklistError("localexec result did not report completed")
        evidence = local_result.get("evidence")
        if not isinstance(evidence, Mapping):
            raise CaseWorklistError("localexec result missing evidence object")
        action = str(local_result.get("capability_id", ""))
        if action == "comfyx-studio.director.preproduction":
            return self._require_keys(evidence, step.acceptance)
        if action == "comfyx-studio.storyboard.plan":
            return self._require_keys(evidence, step.acceptance)
        if action == "presentation.openmaic":
            media = int(evidence.get("media_count", -1))
            if step.step_id.endswith("025"):
                required = int(self._mapping(self._load_spec(self.runtime.load().case_id), "text_storyboard").get("required_media_count", 0))
                if media != required:
                    raise CaseWorklistError(f"text-only storyboard requires media_count={required}, got {media}")
                mapped = {
                    "storyboard_pptx": evidence.get("pptx"),
                    "storyboard_manifest": evidence.get("manifest"),
                    "storyboard_pptx_sha256": evidence.get("sha256"),
                    "slide_count": evidence.get("slide_count"),
                    "reopen_receipt": evidence.get("reopen_receipt") or evidence.get("receipt"),
                    "image_count": media,
                }
            else:
                minimum = int(self._mapping(self._load_spec(self.runtime.load().case_id), "illustrated_storyboard").get("minimum_media_count", 1))
                if media < minimum:
                    raise CaseWorklistError(f"illustrated storyboard requires media_count>={minimum}, got {media}")
                mapped = {
                    "illustrated_storyboard_pptx": evidence.get("pptx"),
                    "illustrated_storyboard_manifest": evidence.get("manifest"),
                    "illustrated_storyboard_sha256": evidence.get("sha256"),
                    "slide_count": evidence.get("slide_count"),
                    "reopen_receipt": evidence.get("reopen_receipt") or evidence.get("receipt"),
                    "bound_image_count": media,
                }
            return self._require_keys(mapped, step.acceptance)
        if action == "comfyx-studio.finalize":
            final = evidence
            qc = final.get("physical_qc")
            mapped = {
                "final_mp4": final.get("final_mp4"),
                "final_mp4_sha256": final.get("final_mp4_sha256"),
                "resolution": final.get("resolution") or "physical_qc",
                "duration": final.get("duration") or "physical_qc",
                "subtitle_receipt": final.get("subtitle_receipt") or "see finalize receipt",
                "physical_qc": qc,
            }
            return self._require_keys(mapped, step.acceptance)
        raise NotImplementedError(f"acceptance mapper is not registered for {action}")

    def _execute_local_claim(self, claim_path: Path) -> dict[str, Any]:
        go_tool_root = Path(os.environ.get("GO_TOOL_ROOT", "")).expanduser()
        if not str(go_tool_root).strip() or not go_tool_root.is_dir():
            raise CaseWorklistError("GO_TOOL_ROOT must point to the local go-tool-runtime checkout")
        executable = os.environ.get("GTR_LOCAL_EXEC_EXE", "").strip()
        if executable:
            argv = [executable, "--claim", str(claim_path)]
        else:
            argv = ["go", "run", "./cmd/gtr-local-exec", "--claim", str(claim_path)]
        proc = subprocess.run(argv, cwd=go_tool_root, env=os.environ.copy(), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise CaseWorklistError(f"gtr-local-exec failed rc={proc.returncode}: {proc.stderr.strip()} {proc.stdout.strip()}")
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        raise CaseWorklistError("gtr-local-exec returned no JSON result")

    def _localexec_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in (
            "GO_TOOL_ROOT", "GTR_LOCAL_EXEC_EXE", "OPENWORKER_ROOT", "COMFYX_ROOT",
            "COMFYX_STUDIO_ROOT", "OPENMAIC_ROOT", "COMFYX_COMFYUI_OUTPUT_ROOT",
            "COMFYX_COMFYUI_INPUT_ROOT", "AI_SHARED_STATE_ROOT", "TERRAIN_ROOT",
        ):
            value = os.environ.get(key, "").strip()
            if value:
                env[key] = value
        env.setdefault("OPENWORKER_ROOT", str(self.openworker_root))
        env["OPENWORKER_CASE_SPEC"] = str(self.spec_path)
        return env

    def _assert_local_node(self, worklist: CaseWorklist) -> None:
        status = self.node.node_status()
        actual = str(status.get("machine", "")).strip()
        if actual.lower() != worklist.assigned_host.lower():
            raise CaseWorklistError(f"local node machine mismatch expected={worklist.assigned_host} actual={actual}")
        if not bool(status.get("online", True)):
            raise CaseWorklistError("local OpenWorker node is not online")

    def _load_spec(self, case_id: str) -> dict[str, Any]:
        spec = self._load_json(self.spec_path)
        if str(spec.get("case_id", "")).strip() != case_id:
            raise CaseWorklistError("persisted case spec case_id mismatch")
        return spec

    @staticmethod
    def _mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        value = source.get(key)
        if not isinstance(value, Mapping):
            raise CaseWorklistError(f"case spec missing {key} object")
        return value

    @staticmethod
    def _require_keys(source: Mapping[str, Any], keys: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        missing: list[str] = []
        for key in keys:
            value = source.get(key)
            if value is None or value == "" or value == []:
                missing.append(key)
            else:
                out[key] = value
        if missing:
            raise CaseWorklistError("local result missing acceptance evidence: " + ", ".join(missing))
        return out

    @staticmethod
    def _execution_id(case_id: str, step_id: str, action: str, revision: int) -> str:
        safe_action = "".join(ch if ch.isalnum() else "-" for ch in action).strip("-")
        return f"case{case_id}-{step_id}-{safe_action}-r{revision}".lower()

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CaseWorklistError(f"cannot read JSON authority: {path}") from exc
        if not isinstance(value, dict):
            raise CaseWorklistError(f"JSON authority must be an object: {path}")
        return value

    @staticmethod
    def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def _write_controller_receipt(self, value: Mapping[str, Any]) -> None:
        self._write_json_atomic(self.workspace / ".openworker" / _CONTROLLER_RECEIPT, value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenWorker local event-driven CaseWorklist controller")
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
    return parser


def main() -> int:
    args = _parser().parse_args()
    controller = LocalCaseController(args.workspace, node_url=args.node_url, spec_path=getattr(args, "spec", None))
    try:
        if args.command == "bootstrap":
            result = controller.bootstrap(args.manifest, args.spec)
        elif args.command == "dispatch":
            result = controller.dispatch_ready()
        else:
            result = controller.run_step(step_id=args.step_id, action_id=args.action_id, execution_id=args.execution_id, claim_path=args.claim)
    except Exception as exc:
        print(json.dumps({"status":"failed","error":str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.command != "run-step":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
