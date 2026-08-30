"""Case 0005 Snow White local-first controller extensions.

The generic LocalCaseController remains reusable. This module only adds the
Case 0005 business mappings that depend on the REAL storyboard visual plan.
OpenWorker Go remains the durable scheduler; ComfyX remains the IMAGE/VIDEO
execution authority and knowledge-graph owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from .case_controller import LocalCaseController
from .case_worklist import CaseStep, CaseWorklist, CaseWorklistError, StepStatus

_VIDEO_STEP_ID = "0005-060"
_VIDEO_ACTION = "comfyx.production.video.real"


class Case0005Controller(LocalCaseController):
    def _claim_inputs(
        self,
        worklist: CaseWorklist,
        step: CaseStep,
        action: str,
        spec: Mapping[str, Any],
    ) -> dict[str, Any]:
        common = {"workspace_root": str(self.workspace), "assigned_host": worklist.assigned_host}
        if action == "image.comfyx.storyboard-real":
            if step.step_id == "0005-030":
                return {**common, "role": "character_master", "requirements_relpath": "visual-assets/requirements.json"}
            if step.step_id == "0005-040":
                return {**common, "role": "scene_concept", "requirements_relpath": "visual-assets/requirements.json"}
        if action == "comfyx-studio.storyboard.real-bind" and step.step_id == "0005-050":
            return {
                **common,
                "request_relpath": "presentation/storyboard-request.json",
                "output_relpath": "presentation/storyboard-request.bound.json",
            }
        return super()._claim_inputs(worklist, step, action, spec)

    def _dispatch_step(
        self,
        worklist: CaseWorklist,
        step: CaseStep,
        spec: Mapping[str, Any],
    ) -> dict[str, Any]:
        if step.step_id == _VIDEO_STEP_ID:
            if step.allowed_actions != [_VIDEO_ACTION]:
                raise CaseWorklistError("0005-060 must have exactly comfyx.production.video.real as its action")
            return self._dispatch_video_fanout(worklist, step, _VIDEO_ACTION)
        return super()._dispatch_step(worklist, step, spec)

    def _dispatch_video_fanout(self, worklist: CaseWorklist, step: CaseStep, action: str) -> dict[str, Any]:
        shots = self._approved_video_shots()
        if not shots:
            raise CaseWorklistError("0005-060 requires at least one approved shot first frame")
        max_slots = int(worklist.parallel_policy.get("max_local_slots", 4) or 4)
        if max_slots < 1:
            raise CaseWorklistError("parallel_policy.max_local_slots must be >= 1")

        group_id = self._execution_id(worklist.case_id, step.step_id, action, worklist.revision)
        fanout_dir = self.workspace / ".openworker" / "fanout" / group_id
        claims_dir = fanout_dir / "claims"
        results_dir = fanout_dir / "results"
        claims_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        jobs: list[dict[str, Any]] = []
        for index, shot in enumerate(shots, start=1):
            child_id = f"{group_id}--shot-{index:03d}-{self._safe_id(shot['shot_id'])}"
            output_relpath = f"video/shots/{self._safe_id(shot['shot_id'])}.mp4"
            claim_path = claims_dir / f"{child_id}.json"
            claim = {
                "work_id": child_id,
                "assigned_host": worklist.assigned_host,
                "capability_id": action,
                "inputs": {
                    "workspace_root": str(self.workspace),
                    "assigned_host": worklist.assigned_host,
                    "shot_id": shot["shot_id"],
                    "first_frame_relpath": shot["first_frame_relpath"],
                    "output_relpath": output_relpath,
                },
                "claimed_by": "openworker-local-case0005-video-fanout",
                "lease_token": child_id,
                "parent_execution_id": group_id,
            }
            self._write_json_atomic(claim_path, claim)
            jobs.append(
                {
                    "shot_id": shot["shot_id"],
                    "first_frame_relpath": shot["first_frame_relpath"],
                    "first_frame_sha256": shot["first_frame_sha256"],
                    "output_relpath": output_relpath,
                    "job_id": child_id,
                    "claim_path": str(claim_path),
                    "result_path": str(results_dir / f"{child_id}.json"),
                }
            )

        manifest_path = fanout_dir / "fanout-manifest.json"
        manifest = {
            "schema_version": "openworker-case0005-video-fanout/v1",
            "case_id": worklist.case_id,
            "step_id": step.step_id,
            "action_id": action,
            "group_execution_id": group_id,
            "assigned_host": worklist.assigned_host,
            "max_local_slots": max_slots,
            "jobs": jobs,
        }
        self._write_json_atomic(manifest_path, manifest)

        self.runtime.start_action(step.step_id, action, execution_id=group_id)
        self.runtime.record(step.step_id, "fanout_manifest", str(manifest_path))
        self.runtime.record(step.step_id, "shot_job_ids", [job["job_id"] for job in jobs])

        accepted: list[dict[str, Any]] = []
        try:
            for job in jobs:
                payload = self._video_child_payload(
                    worklist=worklist,
                    group_id=group_id,
                    child_id=job["job_id"],
                    shot_id=job["shot_id"],
                    claim_path=Path(job["claim_path"]),
                    manifest_path=manifest_path,
                )
                ack = self.node.submit(payload)
                if not bool(ack.get("accepted")):
                    raise CaseWorklistError(f"local OpenWorker did not durably accept video child {job['job_id']}")
                accepted.append({"job_id": job["job_id"], "shot_id": job["shot_id"], "durable_ack": ack})
        except Exception as exc:
            for item in accepted:
                try:
                    self.node.cancel(item["job_id"])
                except Exception:
                    pass
            try:
                self.runtime.block_active(step.step_id, f"video fanout submit failed: {exc}")
            except Exception:
                pass
            raise

        return {
            "step_id": step.step_id,
            "action_id": action,
            "execution_id": group_id,
            "fanout_manifest": str(manifest_path),
            "shot_job_ids": [job["job_id"] for job in jobs],
            "durable_children": accepted,
            "max_local_slots": max_slots,
            "github_action_used_for_business_execution": False,
        }

    def _video_child_payload(
        self,
        *,
        worklist: CaseWorklist,
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
            "coworker.case0005_controller",
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

    def run_video_shot(
        self,
        *,
        group_execution_id: str,
        child_job_id: str,
        shot_id: str,
        claim_path: str | Path,
        fanout_manifest: str | Path,
    ) -> dict[str, Any]:
        manifest_path = Path(fanout_manifest).resolve()
        manifest = self._load_json(manifest_path)
        self._assert_video_child_identity(
            manifest,
            group_execution_id=group_execution_id,
            child_job_id=child_job_id,
            shot_id=shot_id,
            claim_path=Path(claim_path).resolve(),
        )
        result_path = self._fanout_result_path(manifest, child_job_id)
        try:
            local_result = self._execute_local_claim(Path(claim_path))
            if str(local_result.get("status", "")).lower() != "completed":
                raise CaseWorklistError(f"video child {child_job_id} localexec did not report completed")
            evidence = local_result.get("evidence")
            if not isinstance(evidence, Mapping):
                raise CaseWorklistError(f"video child {child_job_id} missing evidence")
            receipt = str(evidence.get("receipt", "")).strip()
            video = str(evidence.get("workspace_mp4", "")).strip()
            sha256 = str(evidence.get("sha256", "")).strip().lower()
            if not receipt or not video or len(sha256) != 64:
                raise CaseWorklistError(f"video child {child_job_id} missing receipt/video/sha256")
            video_path = Path(video).resolve()
            if not video_path.is_file() or video_path.stat().st_size <= 0:
                raise CaseWorklistError(f"video child {child_job_id} canonical MP4 missing or empty")
            if self._sha256_file(video_path) != sha256:
                raise CaseWorklistError(f"video child {child_job_id} canonical MP4 SHA256 mismatch")
            child_result = {
                "status": "succeeded",
                "group_execution_id": group_execution_id,
                "job_id": child_job_id,
                "shot_id": shot_id,
                "receipt": receipt,
                "workspace_mp4": video,
                "sha256": sha256,
                "plan": evidence.get("plan"),
                "durable_graph": evidence.get("durable_graph"),
            }
        except Exception as exc:
            child_result = {
                "status": "failed",
                "group_execution_id": group_execution_id,
                "job_id": child_job_id,
                "shot_id": shot_id,
                "error": str(exc),
            }
            self._write_json_atomic(result_path, child_result)
            self._try_finalize_video_fanout(manifest_path)
            raise

        self._write_json_atomic(result_path, child_result)
        aggregate = self._try_finalize_video_fanout(manifest_path)
        return {"child": child_result, "aggregate": aggregate}

    def _try_finalize_video_fanout(self, manifest_path: Path) -> dict[str, Any]:
        manifest = self._load_json(manifest_path)
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise CaseWorklistError("video fanout manifest has no jobs")
        results: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, Mapping):
                raise CaseWorklistError("video fanout manifest job is invalid")
            path = Path(str(job.get("result_path", ""))).resolve()
            if not path.is_file():
                return {"status": "waiting", "completed": len(results), "total": len(jobs)}
            value = self._load_json(path)
            results.append(value)

        group_id = str(manifest.get("group_execution_id", "")).strip()
        worklist = self.runtime.load()
        step = worklist.step(_VIDEO_STEP_ID)
        if step.status == StepStatus.PASSED:
            return {"status": "already-passed", "total": len(results)}
        failures = [item for item in results if str(item.get("status", "")).lower() != "succeeded"]
        if failures:
            if step.status == StepStatus.RUNNING:
                active = str(step.evidence.get("__openworker_active_execution", "") or "").strip()
                if active == group_id:
                    self.runtime.block_active(
                        _VIDEO_STEP_ID,
                        "video fanout child failure: " + "; ".join(
                            f"{item.get('shot_id')}: {item.get('error', 'failed')}" for item in failures
                        ),
                    )
            return {"status": "blocked", "failures": failures, "total": len(results)}

        shot_job_ids = [str(item["job_id"]) for item in results]
        receipts = [str(item["receipt"]) for item in results]
        videos = [str(item["workspace_mp4"]) for item in results]
        hashes = [str(item["sha256"]) for item in results]
        ledger = [
            {
                "job_id": item["job_id"],
                "shot_id": item["shot_id"],
                "status": "succeeded",
                "receipt": item["receipt"],
                "workspace_mp4": item["workspace_mp4"],
                "sha256": item["sha256"],
                "plan": item.get("plan"),
                "durable_graph": item.get("durable_graph"),
            }
            for item in results
        ]
        evidence = {
            "shot_job_ids": shot_job_ids,
            "shot_video_receipts": receipts,
            "shot_videos": videos,
            "shot_video_sha256": hashes,
            "execution_ledger": ledger,
            "all_shots_terminal_succeeded": True,
        }
        try:
            self.runtime.accept_action_evidence(
                _VIDEO_STEP_ID,
                _VIDEO_ACTION,
                execution_id=group_id,
                evidence=evidence,
            )
        except CaseWorklistError:
            latest = self.runtime.load().step(_VIDEO_STEP_ID)
            if latest.status != StepStatus.PASSED:
                raise
        downstream = self.dispatch_ready()
        return {"status": "passed", "total": len(results), "evidence": evidence, "downstream": downstream}

    def _approved_video_shots(self) -> list[dict[str, str]]:
        bound_path = self.workspace / "presentation" / "storyboard-request.bound.json"
        if not bound_path.is_file():
            raise CaseWorklistError("approved bound storyboard request is missing for video fanout")
        request = self._load_json(bound_path)
        slides = request.get("slides")
        if not isinstance(slides, list):
            raise CaseWorklistError("bound storyboard request missing slides array")
        shots: list[dict[str, str]] = []
        seen: set[str] = set()
        for slide in slides:
            if not isinstance(slide, Mapping) or str(slide.get("kind", "")) != "shot":
                continue
            shot_id = str(slide.get("shot_id", "")).strip()
            image = slide.get("image")
            if not shot_id or not isinstance(image, Mapping):
                raise CaseWorklistError("every shot slide requires shot_id and verified image binding")
            if str(image.get("image_role", "")).strip() != "shot_storyboard":
                raise CaseWorklistError(f"shot {shot_id} first frame must have role=shot_storyboard")
            rel = str(image.get("image_path", "")).strip()
            want_sha = str(image.get("image_sha256", "")).strip().lower()
            if not rel or len(want_sha) != 64:
                raise CaseWorklistError(f"shot {shot_id} image binding missing path or sha256")
            path = (self.workspace / rel).resolve()
            try:
                path.relative_to(self.workspace)
            except ValueError as exc:
                raise CaseWorklistError(f"shot {shot_id} image path escapes workspace") from exc
            if not path.is_file() or path.stat().st_size <= 0:
                raise CaseWorklistError(f"shot {shot_id} first frame missing or empty")
            if self._sha256_file(path) != want_sha:
                raise CaseWorklistError(f"shot {shot_id} first frame SHA256 mismatch")
            if shot_id in seen:
                raise CaseWorklistError(f"duplicate shot_id in bound storyboard: {shot_id}")
            seen.add(shot_id)
            shots.append(
                {
                    "shot_id": shot_id,
                    "first_frame_relpath": path.relative_to(self.workspace).as_posix(),
                    "first_frame_sha256": want_sha,
                }
            )
        return shots

    def _assert_video_child_identity(
        self,
        manifest: Mapping[str, Any],
        *,
        group_execution_id: str,
        child_job_id: str,
        shot_id: str,
        claim_path: Path,
    ) -> None:
        if str(manifest.get("group_execution_id", "")) != group_execution_id:
            raise CaseWorklistError("video child group execution id mismatch")
        worklist = self.runtime.load()
        step = worklist.step(_VIDEO_STEP_ID)
        active = str(step.evidence.get("__openworker_active_execution", "") or "").strip()
        action = str(step.evidence.get("__openworker_active_action", "") or "").strip()
        if step.status != StepStatus.RUNNING or active != group_execution_id or action != _VIDEO_ACTION:
            raise CaseWorklistError("video child no longer owns an active 0005-060 fanout")
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list):
            raise CaseWorklistError("video fanout manifest jobs missing")
        match = next((job for job in jobs if isinstance(job, Mapping) and str(job.get("job_id", "")) == child_job_id), None)
        if match is None:
            raise CaseWorklistError("video child job id is not declared in fanout manifest")
        if str(match.get("shot_id", "")) != shot_id:
            raise CaseWorklistError("video child shot id mismatch")
        if Path(str(match.get("claim_path", ""))).resolve() != claim_path:
            raise CaseWorklistError("video child claim path mismatch")

    def _fanout_result_path(self, manifest: Mapping[str, Any], child_job_id: str) -> Path:
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list):
            raise CaseWorklistError("video fanout manifest jobs missing")
        for job in jobs:
            if isinstance(job, Mapping) and str(job.get("job_id", "")) == child_job_id:
                path = Path(str(job.get("result_path", ""))).resolve()
                try:
                    path.relative_to(self.workspace)
                except ValueError as exc:
                    raise CaseWorklistError("video child result path escapes workspace") from exc
                return path
        raise CaseWorklistError("video child result path not declared")

    def _acceptance_evidence(self, step: CaseStep, local_result: Mapping[str, Any]) -> dict[str, Any]:
        action = str(local_result.get("capability_id", ""))
        if action == "comfyx-studio.storyboard.plan" and step.step_id == "0005-020":
            evidence = local_result.get("evidence")
            if not isinstance(evidence, Mapping):
                raise CaseWorklistError("0005-020 storyboard plan missing evidence")
            actual = str(evidence.get("director_plan_sha256", "")).strip().lower()
            parent = self.runtime.load().step("0005-010")
            expected = str(parent.evidence.get("director_plan_sha256", "")).strip().lower()
            if not expected:
                raise CaseWorklistError("0005-020 requires durable 0005-010 director_plan_sha256 evidence")
            if actual != expected:
                raise CaseWorklistError(
                    f"0005-020 Director provenance mismatch expected={expected} actual={actual}"
                )
            return super()._acceptance_evidence(step, local_result)
        if action == "presentation.openmaic" and step.step_id == "0005-025":
            evidence = local_result.get("evidence")
            if not isinstance(evidence, Mapping):
                raise CaseWorklistError("0005-025 OpenMAIC missing evidence")
            request_path = self.workspace / "presentation" / "storyboard-request.json"
            if not request_path.is_file():
                raise CaseWorklistError("0005-025 canonical storyboard request is missing")
            expected_request_sha = self._sha256_file(request_path)
            actual_request_sha = str(evidence.get("request_sha256", "")).strip().lower()
            if actual_request_sha != expected_request_sha:
                raise CaseWorklistError(
                    f"0005-025 request provenance mismatch expected={expected_request_sha} actual={actual_request_sha}"
                )
            return super()._acceptance_evidence(step, local_result)
        if action == "image.comfyx.storyboard-real" and step.step_id in {"0005-030", "0005-040"}:
            if str(local_result.get("status", "")).lower() != "completed":
                raise CaseWorklistError("ComfyX storyboard IMAGE batch did not report completed")
            evidence = local_result.get("evidence")
            if not isinstance(evidence, Mapping):
                raise CaseWorklistError("ComfyX storyboard IMAGE batch missing evidence")
            receipts = evidence.get("receipts")
            images = evidence.get("images")
            hashes = evidence.get("sha256")
            if not isinstance(receipts, list) or not receipts:
                raise CaseWorklistError("ComfyX storyboard IMAGE batch returned no receipts")
            if not isinstance(images, list) or len(images) != len(receipts):
                raise CaseWorklistError("ComfyX storyboard IMAGE batch image count mismatch")
            if not isinstance(hashes, list) or len(hashes) != len(receipts):
                raise CaseWorklistError("ComfyX storyboard IMAGE batch sha256 count mismatch")
            if step.step_id == "0005-030":
                if str(evidence.get("role", "")) != "character_master":
                    raise CaseWorklistError("0005-030 requires character_master role evidence")
                mapped = {"character_receipts": receipts, "character_images": images, "character_sha256": hashes}
            else:
                if str(evidence.get("role", "")) != "scene_concept":
                    raise CaseWorklistError("0005-040 requires scene_concept role evidence")
                mapped = {"scene_receipts": receipts, "scene_images": images, "scene_sha256": hashes}
            return self._require_keys(mapped, step.acceptance)
        if action == "comfyx-studio.storyboard.real-bind" and step.step_id == "0005-050":
            if str(local_result.get("status", "")).lower() != "completed":
                raise CaseWorklistError("shot storyboard REAL bind did not report completed")
            evidence = local_result.get("evidence")
            if not isinstance(evidence, Mapping):
                raise CaseWorklistError("shot storyboard REAL bind missing evidence")
            mapped = {
                "shot_image_receipts": evidence.get("shot_image_receipts"),
                "shot_images": evidence.get("shot_images"),
                "shot_image_sha256": evidence.get("shot_image_sha256"),
                "bound_storyboard_request": evidence.get("bound_request"),
            }
            receipts = mapped["shot_image_receipts"]
            images = mapped["shot_images"]
            hashes = mapped["shot_image_sha256"]
            if not isinstance(receipts, list) or not receipts:
                raise CaseWorklistError("0005-050 returned no shot image receipts")
            if not isinstance(images, list) or len(images) != len(receipts):
                raise CaseWorklistError("0005-050 shot image count mismatch")
            if not isinstance(hashes, list) or len(hashes) != len(receipts):
                raise CaseWorklistError("0005-050 shot sha256 count mismatch")
            return self._require_keys(mapped, step.acceptance)
        return super()._acceptance_evidence(step, local_result)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_id(value: str) -> str:
        text = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip())
        return text or "item"

    def _job_payload(
        self,
        worklist: CaseWorklist,
        step: CaseStep,
        action: str,
        execution_id: str,
        claim_path: Path,
    ) -> dict[str, Any]:
        python = sys.executable or "python"
        argv = [
            python, "-m", "coworker.case0005_controller", "run-step",
            "--workspace", str(self.workspace), "--step-id", step.step_id,
            "--action-id", action, "--execution-id", execution_id, "--claim", str(claim_path),
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Case 0005 Snow White local-first controller")
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
    video.add_argument("--group-execution-id", required=True)
    video.add_argument("--child-job-id", required=True)
    video.add_argument("--shot-id", required=True)
    video.add_argument("--claim", required=True)
    video.add_argument("--fanout-manifest", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    controller = Case0005Controller(args.workspace, node_url=args.node_url, spec_path=getattr(args, "spec", None))
    try:
        if args.command == "bootstrap":
            result = controller.bootstrap(args.manifest, args.spec)
        elif args.command == "dispatch":
            result = controller.dispatch_ready()
        elif args.command == "run-video-shot":
            result = controller.run_video_shot(
                group_execution_id=args.group_execution_id,
                child_job_id=args.child_job_id,
                shot_id=args.shot_id,
                claim_path=args.claim,
                fanout_manifest=args.fanout_manifest,
            )
        else:
            result = controller.run_step(
                step_id=args.step_id,
                action_id=args.action_id,
                execution_id=args.execution_id,
                claim_path=args.claim,
            )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.command != "run-step":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
