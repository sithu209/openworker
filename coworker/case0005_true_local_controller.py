"""Case 0005 true local supervisor controller.

This is the final Case-0005 orchestration layer used to validate the real
local-supervisor architecture:

  controller -> OpenWorker durable child jobs -> gtr-local-exec compatibility
  client -> go-tool :8848 durable queue -> four claim/execution slots.

Character-master and scene-concept IMAGE work is materialized per asset so the
four local slots have independent durable actions to execute.  The inherited
logged controller keeps the append-only Case supervisor ledger; go-tool keeps
its own append-only work/slot/executor ledger.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

from .case0005_logged_controller import LoggedCase0005Controller
from .case_worklist import CaseStep, CaseWorklist, CaseWorklistError, StepStatus

_IMAGE_ACTION = "image.comfyx.storyboard-real"
_IMAGE_STEPS = {
    "0005-030": "character_master",
    "0005-040": "scene_concept",
}


class TrueLocalCase0005Controller(LoggedCase0005Controller):
    def _dispatch_step(self, worklist: CaseWorklist, step: CaseStep, spec: Mapping[str, Any]) -> dict[str, Any]:
        if step.step_id in _IMAGE_STEPS:
            if step.allowed_actions != [_IMAGE_ACTION]:
                raise CaseWorklistError(f"{step.step_id} must have exactly {_IMAGE_ACTION} as its action")
            self._append_ledger(
                "step_dispatch_start",
                step_id=step.step_id,
                action_id=_IMAGE_ACTION,
                worklist_revision=worklist.revision,
                step_kind=step.kind,
                execution_route="local_supervisor",
            )
            try:
                result = self._dispatch_image_fanout(worklist, step, _IMAGE_ACTION, _IMAGE_STEPS[step.step_id])
            except Exception as exc:
                self._append_ledger(
                    "step_dispatch_failed",
                    step_id=step.step_id,
                    action_id=_IMAGE_ACTION,
                    error=str(exc),
                    execution_route="local_supervisor",
                )
                raise
            self._append_ledger(
                "step_durable_accepted",
                step_id=step.step_id,
                action_id=_IMAGE_ACTION,
                execution_id=str(result.get("execution_id", "")),
                fanout_manifest=result.get("fanout_manifest"),
                child_job_ids=result.get("asset_job_ids"),
                max_local_slots=result.get("max_local_slots"),
                execution_route="local_supervisor",
                github_action_used_for_business_execution=False,
            )
            return result
        return super()._dispatch_step(worklist, step, spec)

    def _dispatch_image_fanout(
        self,
        worklist: CaseWorklist,
        step: CaseStep,
        action: str,
        role: str,
    ) -> dict[str, Any]:
        assets = self._visual_assets_for_role(role)
        if not assets:
            raise CaseWorklistError(f"{step.step_id} requires at least one {role} asset")
        max_slots = int(worklist.parallel_policy.get("max_local_slots", 4) or 4)
        if max_slots != 4:
            raise CaseWorklistError(f"Case 0005 true-local validation requires max_local_slots=4, got {max_slots}")

        group_id = self._execution_id(worklist.case_id, step.step_id, action, worklist.revision)
        fanout_dir = self.workspace / ".openworker" / "fanout" / group_id
        claims_dir = fanout_dir / "claims"
        results_dir = fanout_dir / "results"
        claims_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        jobs: list[dict[str, Any]] = []
        for index, asset_id in enumerate(assets, start=1):
            safe_asset = self._safe_id(asset_id)
            child_id = f"{group_id}--asset-{index:03d}-{safe_asset}"
            claim_path = claims_dir / f"{child_id}.json"
            result_path = results_dir / f"{child_id}.json"
            claim = {
                "work_id": child_id,
                "assigned_host": worklist.assigned_host,
                "capability_id": action,
                "inputs": {
                    "workspace_root": str(self.workspace),
                    "assigned_host": worklist.assigned_host,
                    "asset_id": asset_id,
                    "requirements_relpath": "visual-assets/requirements.json",
                },
                "claimed_by": "openworker-case0005-true-local-image-fanout",
                "lease_token": child_id,
                "parent_execution_id": group_id,
            }
            self._write_json_atomic(claim_path, claim)
            jobs.append({
                "asset_id": asset_id,
                "role": role,
                "job_id": child_id,
                "claim_path": str(claim_path),
                "result_path": str(result_path),
            })

        manifest_path = fanout_dir / "fanout-manifest.json"
        manifest = {
            "schema_version": "openworker-case0005-image-fanout/v1",
            "case_id": worklist.case_id,
            "step_id": step.step_id,
            "action_id": action,
            "role": role,
            "group_execution_id": group_id,
            "assigned_host": worklist.assigned_host,
            "max_local_slots": max_slots,
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
            "jobs": jobs,
        }
        self._write_json_atomic(manifest_path, manifest)

        self.runtime.start_action(step.step_id, action, execution_id=group_id)
        self.runtime.record(step.step_id, "fanout_manifest", str(manifest_path))
        self.runtime.record(step.step_id, "asset_job_ids", [job["job_id"] for job in jobs])
        self.runtime.record(step.step_id, "execution_route", "local_supervisor")

        accepted: list[dict[str, Any]] = []
        try:
            for job in jobs:
                payload = self._image_child_payload(
                    worklist=worklist,
                    step_id=step.step_id,
                    group_id=group_id,
                    child_id=job["job_id"],
                    asset_id=job["asset_id"],
                    role=role,
                    claim_path=Path(job["claim_path"]),
                    manifest_path=manifest_path,
                )
                ack = self.node.submit(payload)
                if not bool(ack.get("accepted")):
                    raise CaseWorklistError(f"local OpenWorker did not durably accept image child {job['job_id']}")
                accepted.append({"job_id": job["job_id"], "asset_id": job["asset_id"], "durable_ack": ack})
                self._append_ledger(
                    "image_child_durable_accepted",
                    step_id=step.step_id,
                    action_id=action,
                    execution_id=job["job_id"],
                    parent_execution_id=group_id,
                    asset_id=job["asset_id"],
                    role=role,
                    durable_ack=ack,
                    execution_route="local_supervisor",
                )
        except Exception as exc:
            for item in accepted:
                try:
                    self.node.cancel(item["job_id"])
                except Exception:
                    pass
            try:
                self.runtime.block_active(step.step_id, f"image fanout submit failed: {exc}")
            except Exception:
                pass
            raise

        return {
            "step_id": step.step_id,
            "action_id": action,
            "execution_id": group_id,
            "fanout_manifest": str(manifest_path),
            "asset_job_ids": [job["job_id"] for job in jobs],
            "durable_children": accepted,
            "max_local_slots": max_slots,
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
        }

    def _image_child_payload(
        self,
        *,
        worklist: CaseWorklist,
        step_id: str,
        group_id: str,
        child_id: str,
        asset_id: str,
        role: str,
        claim_path: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        python = sys.executable or "python"
        argv = [
            python,
            "-m",
            "coworker.case0005_true_local_controller",
            "run-image-asset",
            "--workspace",
            str(self.workspace),
            "--step-id",
            step_id,
            "--group-execution-id",
            group_id,
            "--child-job-id",
            child_id,
            "--asset-id",
            asset_id,
            "--role",
            role,
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
            "locks": [f"case:{worklist.case_id}:image-asset:{self._safe_id(asset_id)}"],
        }

    def run_image_asset(
        self,
        *,
        step_id: str,
        group_execution_id: str,
        child_job_id: str,
        asset_id: str,
        role: str,
        claim_path: str | Path,
        fanout_manifest: str | Path,
    ) -> dict[str, Any]:
        manifest_path = Path(fanout_manifest).resolve()
        manifest = self._load_json(manifest_path)
        self._assert_image_child_identity(
            manifest,
            step_id=step_id,
            group_execution_id=group_execution_id,
            child_job_id=child_job_id,
            asset_id=asset_id,
            role=role,
            claim_path=Path(claim_path).resolve(),
        )
        result_path = self._image_result_path(manifest, child_job_id)
        self._append_ledger(
            "image_child_running",
            step_id=step_id,
            action_id=_IMAGE_ACTION,
            execution_id=child_job_id,
            parent_execution_id=group_execution_id,
            job_id=child_job_id,
            asset_id=asset_id,
            role=role,
            execution_route="local_supervisor",
        )
        try:
            local_result = self._execute_local_claim(Path(claim_path))
            if str(local_result.get("status", "")).lower() != "completed":
                raise CaseWorklistError(f"image child {child_job_id} localexec did not report completed")
            evidence = local_result.get("evidence")
            if not isinstance(evidence, Mapping):
                raise CaseWorklistError(f"image child {child_job_id} missing evidence")
            if str(evidence.get("asset_id", "")).strip() != asset_id:
                raise CaseWorklistError(f"image child {child_job_id} asset_id evidence mismatch")
            receipt = evidence.get("receipt")
            if not isinstance(receipt, Mapping):
                raise CaseWorklistError(f"image child {child_job_id} receipt missing")
            data = receipt.get("data")
            if not isinstance(data, Mapping):
                raise CaseWorklistError(f"image child {child_job_id} receipt data missing")
            rel = str(data.get("workspace_relpath", "")).strip()
            artifact = data.get("workspace_artifact")
            if not isinstance(artifact, Mapping):
                raise CaseWorklistError(f"image child {child_job_id} workspace_artifact missing")
            sha256 = str(artifact.get("sha256", "")).strip().lower()
            if not rel or len(sha256) != 64:
                raise CaseWorklistError(f"image child {child_job_id} path/sha256 missing")
            image_path = (self.workspace / rel).resolve()
            try:
                image_path.relative_to(self.workspace)
            except ValueError as exc:
                raise CaseWorklistError(f"image child {child_job_id} path escapes workspace") from exc
            if not image_path.is_file() or image_path.stat().st_size <= 0:
                raise CaseWorklistError(f"image child {child_job_id} canonical image missing or empty")
            if self._sha256_file(image_path) != sha256:
                raise CaseWorklistError(f"image child {child_job_id} canonical image SHA256 mismatch")
            child_result = {
                "status": "succeeded",
                "step_id": step_id,
                "group_execution_id": group_execution_id,
                "job_id": child_job_id,
                "asset_id": asset_id,
                "role": role,
                "receipt": receipt,
                "workspace_image": str(image_path),
                "sha256": sha256,
            }
        except Exception as exc:
            child_result = {
                "status": "failed",
                "step_id": step_id,
                "group_execution_id": group_execution_id,
                "job_id": child_job_id,
                "asset_id": asset_id,
                "role": role,
                "error": str(exc),
            }
            self._write_json_atomic(result_path, child_result)
            self._append_ledger("image_child_failed", **child_result, execution_route="local_supervisor")
            self._try_finalize_image_fanout(manifest_path)
            raise

        self._write_json_atomic(result_path, child_result)
        self._append_ledger("image_child_passed", **child_result, execution_route="local_supervisor")
        aggregate = self._try_finalize_image_fanout(manifest_path)
        return {"child": child_result, "aggregate": aggregate}

    def _try_finalize_image_fanout(self, manifest_path: Path) -> dict[str, Any]:
        manifest = self._load_json(manifest_path)
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise CaseWorklistError("image fanout manifest has no jobs")
        results: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, Mapping):
                raise CaseWorklistError("image fanout manifest job is invalid")
            path = Path(str(job.get("result_path", ""))).resolve()
            if not path.is_file():
                return {"status": "waiting", "completed": len(results), "total": len(jobs)}
            results.append(self._load_json(path))

        step_id = str(manifest.get("step_id", "")).strip()
        group_id = str(manifest.get("group_execution_id", "")).strip()
        role = str(manifest.get("role", "")).strip()
        worklist = self.runtime.load()
        step = worklist.step(step_id)
        if step.status == StepStatus.PASSED:
            return {"status": "already-passed", "total": len(results)}
        failures = [item for item in results if str(item.get("status", "")).lower() != "succeeded"]
        if failures:
            if step.status == StepStatus.RUNNING:
                active = str(step.evidence.get("__openworker_active_execution", "") or "").strip()
                if active == group_id:
                    self.runtime.block_active(
                        step_id,
                        "image fanout child failure: " + "; ".join(
                            f"{item.get('asset_id')}: {item.get('error', 'failed')}" for item in failures
                        ),
                    )
            return {"status": "blocked", "failures": failures, "total": len(results)}

        receipts = [item["receipt"] for item in results]
        images = [str(item["workspace_image"]) for item in results]
        hashes = [str(item["sha256"]) for item in results]
        asset_ids = [str(item["asset_id"]) for item in results]
        execution_ledger = [
            {
                "job_id": item["job_id"],
                "asset_id": item["asset_id"],
                "role": item["role"],
                "status": "succeeded",
                "workspace_image": item["workspace_image"],
                "sha256": item["sha256"],
            }
            for item in results
        ]
        if step_id == "0005-030":
            evidence = {
                "character_receipts": receipts,
                "character_images": images,
                "character_sha256": hashes,
                "asset_ids": asset_ids,
                "execution_ledger": execution_ledger,
                "all_assets_terminal_succeeded": True,
            }
        elif step_id == "0005-040":
            evidence = {
                "scene_receipts": receipts,
                "scene_images": images,
                "scene_sha256": hashes,
                "asset_ids": asset_ids,
                "execution_ledger": execution_ledger,
                "all_assets_terminal_succeeded": True,
            }
        else:
            raise CaseWorklistError(f"unsupported image fanout step {step_id}")
        required = step.acceptance
        for key in required:
            value = evidence.get(key)
            if value is None or value == "" or value == []:
                raise CaseWorklistError(f"image fanout acceptance missing {key}")
        try:
            self.runtime.accept_action_evidence(step_id, _IMAGE_ACTION, execution_id=group_id, evidence=evidence)
        except CaseWorklistError:
            latest = self.runtime.load().step(step_id)
            if latest.status != StepStatus.PASSED:
                raise
        self._append_ledger(
            "image_fanout_passed",
            step_id=step_id,
            action_id=_IMAGE_ACTION,
            execution_id=group_id,
            role=role,
            child_count=len(results),
            max_local_slots=int(manifest.get("max_local_slots", 4) or 4),
            evidence=evidence,
            execution_route="local_supervisor",
        )
        downstream = self.dispatch_ready()
        return {"status": "passed", "total": len(results), "evidence": evidence, "downstream": downstream}

    def _visual_assets_for_role(self, role: str) -> list[str]:
        path = self.workspace / "visual-assets" / "requirements.json"
        if not path.is_file():
            raise CaseWorklistError("visual-assets/requirements.json is missing")
        value = self._load_json(path)
        requirements = value.get("requirements")
        if not isinstance(requirements, list):
            raise CaseWorklistError("visual requirements missing requirements array")
        out: list[str] = []
        seen: set[str] = set()
        for item in requirements:
            if not isinstance(item, Mapping) or str(item.get("role", "")).strip() != role:
                continue
            asset_id = str(item.get("asset_id", "")).strip()
            if not asset_id:
                raise CaseWorklistError(f"{role} contains empty asset_id")
            if asset_id in seen:
                raise CaseWorklistError(f"duplicate asset_id in {role}: {asset_id}")
            seen.add(asset_id)
            out.append(asset_id)
        return out

    def _assert_image_child_identity(
        self,
        manifest: Mapping[str, Any],
        *,
        step_id: str,
        group_execution_id: str,
        child_job_id: str,
        asset_id: str,
        role: str,
        claim_path: Path,
    ) -> None:
        if str(manifest.get("step_id", "")) != step_id or str(manifest.get("role", "")) != role:
            raise CaseWorklistError("image child step/role mismatch")
        if str(manifest.get("group_execution_id", "")) != group_execution_id:
            raise CaseWorklistError("image child group execution id mismatch")
        worklist = self.runtime.load()
        step = worklist.step(step_id)
        active = str(step.evidence.get("__openworker_active_execution", "") or "").strip()
        action = str(step.evidence.get("__openworker_active_action", "") or "").strip()
        if step.status != StepStatus.RUNNING or active != group_execution_id or action != _IMAGE_ACTION:
            raise CaseWorklistError("image child no longer owns an active fanout")
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list):
            raise CaseWorklistError("image fanout manifest jobs missing")
        match = next((job for job in jobs if isinstance(job, Mapping) and str(job.get("job_id", "")) == child_job_id), None)
        if match is None:
            raise CaseWorklistError("image child job id is not declared in fanout manifest")
        if str(match.get("asset_id", "")) != asset_id:
            raise CaseWorklistError("image child asset id mismatch")
        if Path(str(match.get("claim_path", ""))).resolve() != claim_path:
            raise CaseWorklistError("image child claim path mismatch")

    def _image_result_path(self, manifest: Mapping[str, Any], child_job_id: str) -> Path:
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list):
            raise CaseWorklistError("image fanout manifest jobs missing")
        for job in jobs:
            if isinstance(job, Mapping) and str(job.get("job_id", "")) == child_job_id:
                path = Path(str(job.get("result_path", ""))).resolve()
                try:
                    path.relative_to(self.workspace)
                except ValueError as exc:
                    raise CaseWorklistError("image child result path escapes workspace") from exc
                return path
        raise CaseWorklistError("image child result path not declared")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Case 0005 true local four-slot controller")
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
    controller = TrueLocalCase0005Controller(args.workspace, node_url=args.node_url, spec_path=getattr(args, "spec", None))
    try:
        if args.command == "bootstrap":
            result = controller.bootstrap(args.manifest, args.spec)
        elif args.command == "dispatch":
            result = controller.dispatch_ready()
        elif args.command == "run-step":
            result = controller.run_step(step_id=args.step_id, action_id=args.action_id, execution_id=args.execution_id, claim_path=args.claim)
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
            controller._append_ledger("controller_command_failed", command=args.command, error=str(exc))
        except Exception:
            pass
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.command not in {"run-step", "run-video-shot", "run-image-asset"}:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
