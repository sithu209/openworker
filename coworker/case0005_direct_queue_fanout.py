"""Direct :8848 fanout ownership for Case 0005.

Business fanout items are all durably submitted to go-tool first. OpenWorker
runs only one coordinator job per fanout group to observe terminal results,
validate artifacts, update the Case ledger/worklist, and continue the DAG.
This prevents OpenWorker's process slots from becoming a hidden pre-queue in
front of the true local supervisor.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .case_worklist import CaseWorklistError

_QUEUE_BASE = "http://127.0.0.1:8848"
_IMAGE_ACTION = "image.comfyx.storyboard-real"
_VIDEO_ACTION = "comfyx.production.video.real"
_CANONICAL_MODULE = "coworker.case0005_verified_local_controller"


class Case0005DirectQueueFanoutMixin:
    def _queue_json(self, method: str, path: str, payload: Mapping[str, Any] | None = None, timeout: int = 10) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(_QUEUE_BASE + path, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read(4 * 1024 * 1024)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise CaseWorklistError(f"local supervisor queue request failed {method} {path}: {exc}") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise CaseWorklistError(f"local supervisor queue returned invalid JSON for {path}") from exc
        if not isinstance(value, dict):
            raise CaseWorklistError(f"local supervisor queue returned non-object for {path}")
        return value

    def _queue_submit(self, *, work_id: str, assigned_host: str, capability_id: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
        item = self._queue_json("POST", "/api/execution/local-work", {
            "work_id": work_id,
            "assigned_host": assigned_host,
            "capability_id": capability_id,
            "inputs": inputs,
        })
        if str(item.get("work_id", "")) != work_id:
            raise CaseWorklistError(f"local supervisor returned wrong work_id for {work_id}")
        if str(item.get("capability_id", "")) != capability_id:
            raise CaseWorklistError(f"local supervisor returned wrong capability for {work_id}")
        if str(item.get("assigned_host", "")).lower() != assigned_host.lower():
            raise CaseWorklistError(f"local supervisor returned wrong assigned_host for {work_id}")
        if str(item.get("status", "")) not in {"pending", "claimed", "completed", "failed"}:
            raise CaseWorklistError(f"local supervisor returned invalid status for {work_id}")
        return item

    def _queue_get(self, work_id: str) -> dict[str, Any]:
        return self._queue_json("GET", f"/api/execution/local-work/{work_id}")

    def _coordinator_payload(self, worklist, *, group_id: str, kind: str, manifest_path: Path, timeout_sec: int) -> dict[str, Any]:
        job_id = f"{group_id}--queue-coordinator"
        python = sys.executable or "python"
        command = "watch-image-fanout" if kind == "image" else "watch-video-fanout"
        argv = [
            python, "-m", _CANONICAL_MODULE, command,
            "--workspace", str(self.workspace),
            "--fanout-manifest", str(manifest_path),
        ]
        return {
            "job_id": job_id,
            "dispatch_id": "verified-local-queue-coordinator-" + group_id,
            "machine": worklist.assigned_host,
            "priority": 100,
            "command": subprocess.list2cmdline(argv),
            "cwd": str(self.openworker_root),
            "workspace_root": str(self.workspace),
            "env": self._localexec_env(),
            "timeout_sec": timeout_sec,
            "locks": [f"case:{worklist.case_id}:queue-coordinator:{group_id}"],
        }

    def _dispatch_image_fanout(self, worklist, step, action: str, role: str) -> dict[str, Any]:
        assets = self._visual_assets_for_role(role)
        if not assets:
            raise CaseWorklistError(f"{step.step_id} requires at least one {role} asset")
        max_slots = int(worklist.parallel_policy.get("max_local_slots", 4) or 4)
        if max_slots != 4:
            raise CaseWorklistError(f"Case 0005 true-local validation requires max_local_slots=4, got {max_slots}")
        group_id = self._execution_id(worklist.case_id, step.step_id, action, worklist.revision)
        fanout_dir = self.workspace / ".openworker" / "fanout" / group_id
        results_dir = fanout_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        jobs: list[dict[str, Any]] = []
        for index, asset_id in enumerate(assets, start=1):
            child_id = f"{group_id}--asset-{index:03d}-{self._safe_id(asset_id)}"
            jobs.append({
                "asset_id": asset_id,
                "role": role,
                "job_id": child_id,
                "queue_work_id": child_id,
                "result_path": str(results_dir / f"{child_id}.json"),
                "inputs": {
                    "workspace_root": str(self.workspace),
                    "assigned_host": worklist.assigned_host,
                    "asset_id": asset_id,
                    "requirements_relpath": "visual-assets/requirements.json",
                },
            })
        manifest_path = fanout_dir / "fanout-manifest.json"
        manifest = {
            "schema_version": "openworker-case0005-direct-queue-image-fanout/v2",
            "case_id": worklist.case_id,
            "step_id": step.step_id,
            "action_id": action,
            "role": role,
            "group_execution_id": group_id,
            "assigned_host": worklist.assigned_host,
            "max_local_slots": max_slots,
            "queue_authority": "go-tool-runtime:8848",
            "queue_owns_all_children": True,
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
            "jobs": jobs,
        }
        self._write_json_atomic(manifest_path, manifest)
        self.runtime.start_action(step.step_id, action, execution_id=group_id)
        self.runtime.record(step.step_id, "fanout_manifest", str(manifest_path))
        self.runtime.record(step.step_id, "asset_job_ids", [j["job_id"] for j in jobs])
        self.runtime.record(step.step_id, "execution_route", "local_supervisor")
        self.runtime.record(step.step_id, "queue_authority", "go-tool-runtime:8848")
        accepted: list[dict[str, Any]] = []
        try:
            for job in jobs:
                item = self._queue_submit(
                    work_id=job["queue_work_id"],
                    assigned_host=worklist.assigned_host,
                    capability_id=action,
                    inputs=job["inputs"],
                )
                accepted.append({"work_id": job["queue_work_id"], "asset_id": job["asset_id"], "queue_item": item})
                self._append_ledger(
                    "image_child_local_queue_accepted",
                    step_id=step.step_id,
                    action_id=action,
                    execution_id=job["queue_work_id"],
                    parent_execution_id=group_id,
                    asset_id=job["asset_id"],
                    role=role,
                    queue_status=item.get("status"),
                    queue_authority="go-tool-runtime:8848",
                    execution_route="local_supervisor",
                    github_action_used_for_business_execution=False,
                )
            coordinator = self.node.submit(self._coordinator_payload(worklist, group_id=group_id, kind="image", manifest_path=manifest_path, timeout_sec=5400))
            if not bool(coordinator.get("accepted")):
                raise CaseWorklistError("OpenWorker did not durably accept image queue coordinator")
        except Exception as exc:
            try:
                self.runtime.block_active(step.step_id, f"direct local queue image fanout submit failed: {exc}")
            except Exception:
                pass
            raise
        return {
            "step_id": step.step_id,
            "action_id": action,
            "execution_id": group_id,
            "fanout_manifest": str(manifest_path),
            "asset_job_ids": [j["job_id"] for j in jobs],
            "durable_local_work": accepted,
            "coordinator_ack": coordinator,
            "max_local_slots": max_slots,
            "queue_owns_all_children": True,
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
        }

    def _dispatch_video_fanout(self, worklist, step, action: str) -> dict[str, Any]:
        shots = self._approved_video_shots()
        if not shots:
            raise CaseWorklistError("0005-060 requires at least one approved shot first frame")
        max_slots = int(worklist.parallel_policy.get("max_local_slots", 4) or 4)
        if max_slots != 4:
            raise CaseWorklistError(f"Case 0005 true-local validation requires max_local_slots=4, got {max_slots}")
        group_id = self._execution_id(worklist.case_id, step.step_id, action, worklist.revision)
        fanout_dir = self.workspace / ".openworker" / "fanout" / group_id
        results_dir = fanout_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        jobs: list[dict[str, Any]] = []
        for index, shot in enumerate(shots, start=1):
            child_id = f"{group_id}--shot-{index:03d}-{self._safe_id(shot['shot_id'])}"
            output_relpath = f"video/shots/{self._safe_id(shot['shot_id'])}.mp4"
            jobs.append({
                "shot_id": shot["shot_id"],
                "first_frame_relpath": shot["first_frame_relpath"],
                "first_frame_sha256": shot["first_frame_sha256"],
                "output_relpath": output_relpath,
                "job_id": child_id,
                "queue_work_id": child_id,
                "result_path": str(results_dir / f"{child_id}.json"),
                "inputs": {
                    "workspace_root": str(self.workspace),
                    "assigned_host": worklist.assigned_host,
                    "shot_id": shot["shot_id"],
                    "first_frame_relpath": shot["first_frame_relpath"],
                    "output_relpath": output_relpath,
                },
            })
        manifest_path = fanout_dir / "fanout-manifest.json"
        manifest = {
            "schema_version": "openworker-case0005-direct-queue-video-fanout/v2",
            "case_id": worklist.case_id,
            "step_id": step.step_id,
            "action_id": action,
            "group_execution_id": group_id,
            "assigned_host": worklist.assigned_host,
            "max_local_slots": max_slots,
            "queue_authority": "go-tool-runtime:8848",
            "queue_owns_all_children": True,
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
            "jobs": jobs,
        }
        self._write_json_atomic(manifest_path, manifest)
        self.runtime.start_action(step.step_id, action, execution_id=group_id)
        self.runtime.record(step.step_id, "fanout_manifest", str(manifest_path))
        self.runtime.record(step.step_id, "shot_job_ids", [j["job_id"] for j in jobs])
        self.runtime.record(step.step_id, "execution_route", "local_supervisor")
        self.runtime.record(step.step_id, "queue_authority", "go-tool-runtime:8848")
        accepted: list[dict[str, Any]] = []
        try:
            for job in jobs:
                item = self._queue_submit(
                    work_id=job["queue_work_id"],
                    assigned_host=worklist.assigned_host,
                    capability_id=action,
                    inputs=job["inputs"],
                )
                accepted.append({"work_id": job["queue_work_id"], "shot_id": job["shot_id"], "queue_item": item})
                self._append_ledger(
                    "video_child_local_queue_accepted",
                    step_id=step.step_id,
                    action_id=action,
                    execution_id=job["queue_work_id"],
                    parent_execution_id=group_id,
                    shot_id=job["shot_id"],
                    queue_status=item.get("status"),
                    queue_authority="go-tool-runtime:8848",
                    execution_route="local_supervisor",
                    github_action_used_for_business_execution=False,
                )
            coordinator = self.node.submit(self._coordinator_payload(worklist, group_id=group_id, kind="video", manifest_path=manifest_path, timeout_sec=14400))
            if not bool(coordinator.get("accepted")):
                raise CaseWorklistError("OpenWorker did not durably accept video queue coordinator")
        except Exception as exc:
            try:
                self.runtime.block_active(step.step_id, f"direct local queue video fanout submit failed: {exc}")
            except Exception:
                pass
            raise
        return {
            "step_id": step.step_id,
            "action_id": action,
            "execution_id": group_id,
            "fanout_manifest": str(manifest_path),
            "shot_job_ids": [j["job_id"] for j in jobs],
            "durable_local_work": accepted,
            "coordinator_ack": coordinator,
            "max_local_slots": max_slots,
            "queue_owns_all_children": True,
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
        }

    def _decode_queue_result(self, item: Mapping[str, Any], work_id: str) -> Mapping[str, Any]:
        result = item.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception as exc:
                raise CaseWorklistError(f"local queue result for {work_id} is invalid JSON") from exc
        if not isinstance(result, Mapping):
            raise CaseWorklistError(f"local queue result for {work_id} is missing")
        if str(result.get("status", "")).lower() != "completed":
            raise CaseWorklistError(f"local queue capability result for {work_id} is not completed")
        evidence = result.get("evidence")
        if not isinstance(evidence, Mapping):
            raise CaseWorklistError(f"local queue result for {work_id} has no evidence")
        return evidence

    def watch_image_fanout(self, fanout_manifest: str | Path) -> dict[str, Any]:
        manifest_path = Path(fanout_manifest).resolve()
        manifest = self._load_json(manifest_path)
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise CaseWorklistError("image direct queue fanout manifest has no jobs")
        deadline = time.monotonic() + 5400
        pending = {str(j["queue_work_id"]): j for j in jobs if isinstance(j, Mapping)}
        while pending:
            progressed = False
            for work_id, job in list(pending.items()):
                item = self._queue_get(work_id)
                status = str(item.get("status", ""))
                if status not in {"completed", "failed"}:
                    continue
                progressed = True
                if status == "failed":
                    child = {"status":"failed","step_id":manifest["step_id"],"group_execution_id":manifest["group_execution_id"],"job_id":work_id,"asset_id":job["asset_id"],"role":job["role"],"error":str(item.get("error", "local queue failed"))}
                else:
                    try:
                        evidence = self._decode_queue_result(item, work_id)
                        child = self._image_child_from_queue(manifest, job, evidence)
                    except Exception as exc:
                        child = {"status":"failed","step_id":manifest["step_id"],"group_execution_id":manifest["group_execution_id"],"job_id":work_id,"asset_id":job["asset_id"],"role":job["role"],"error":str(exc)}
                self._write_json_atomic(Path(str(job["result_path"])), child)
                self._append_ledger("image_child_queue_terminal", **child, queue_authority="go-tool-runtime:8848", execution_route="local_supervisor")
                del pending[work_id]
            if pending:
                if time.monotonic() >= deadline:
                    raise CaseWorklistError(f"image queue coordinator timeout; pending={sorted(pending)}")
                time.sleep(0.5 if progressed else 1.0)
        return self._try_finalize_image_fanout(manifest_path)

    def _image_child_from_queue(self, manifest: Mapping[str, Any], job: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
        asset_id = str(job["asset_id"])
        if str(evidence.get("asset_id", "")).strip() != asset_id:
            raise CaseWorklistError(f"image queue evidence asset_id mismatch for {asset_id}")
        receipt = evidence.get("receipt")
        if not isinstance(receipt, Mapping):
            raise CaseWorklistError(f"image queue receipt missing for {asset_id}")
        data = receipt.get("data")
        if not isinstance(data, Mapping):
            raise CaseWorklistError(f"image queue receipt data missing for {asset_id}")
        rel = str(data.get("workspace_relpath", "")).strip()
        artifact = data.get("workspace_artifact")
        if not isinstance(artifact, Mapping):
            raise CaseWorklistError(f"image queue workspace_artifact missing for {asset_id}")
        sha256 = str(artifact.get("sha256", "")).strip().lower()
        if not rel or len(sha256) != 64:
            raise CaseWorklistError(f"image queue path/sha256 missing for {asset_id}")
        path = (self.workspace / rel).resolve()
        try:
            path.relative_to(self.workspace)
        except ValueError as exc:
            raise CaseWorklistError(f"image queue path escapes workspace for {asset_id}") from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise CaseWorklistError(f"image queue artifact missing or empty for {asset_id}")
        if self._sha256_file(path) != sha256:
            raise CaseWorklistError(f"image queue SHA256 mismatch for {asset_id}")
        return {"status":"succeeded","step_id":manifest["step_id"],"group_execution_id":manifest["group_execution_id"],"job_id":job["queue_work_id"],"asset_id":asset_id,"role":job["role"],"receipt":receipt,"workspace_image":str(path),"sha256":sha256}

    def watch_video_fanout(self, fanout_manifest: str | Path) -> dict[str, Any]:
        manifest_path = Path(fanout_manifest).resolve()
        manifest = self._load_json(manifest_path)
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise CaseWorklistError("video direct queue fanout manifest has no jobs")
        deadline = time.monotonic() + 14400
        pending = {str(j["queue_work_id"]): j for j in jobs if isinstance(j, Mapping)}
        while pending:
            progressed = False
            for work_id, job in list(pending.items()):
                item = self._queue_get(work_id)
                status = str(item.get("status", ""))
                if status not in {"completed", "failed"}:
                    continue
                progressed = True
                if status == "failed":
                    child = {"status":"failed","group_execution_id":manifest["group_execution_id"],"job_id":work_id,"shot_id":job["shot_id"],"error":str(item.get("error", "local queue failed"))}
                else:
                    try:
                        evidence = self._decode_queue_result(item, work_id)
                        child = self._video_child_from_queue(manifest, job, evidence)
                    except Exception as exc:
                        child = {"status":"failed","group_execution_id":manifest["group_execution_id"],"job_id":work_id,"shot_id":job["shot_id"],"error":str(exc)}
                self._write_json_atomic(Path(str(job["result_path"])), child)
                self._append_ledger("video_child_queue_terminal", **child, queue_authority="go-tool-runtime:8848", execution_route="local_supervisor")
                del pending[work_id]
            if pending:
                if time.monotonic() >= deadline:
                    raise CaseWorklistError(f"video queue coordinator timeout; pending={sorted(pending)}")
                time.sleep(0.5 if progressed else 1.0)
        return self._try_finalize_video_fanout(manifest_path)

    def _video_child_from_queue(self, manifest: Mapping[str, Any], job: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
        receipt = str(evidence.get("receipt", "")).strip()
        video = str(evidence.get("workspace_mp4", "")).strip()
        sha256 = str(evidence.get("sha256", "")).strip().lower()
        if not receipt or not video or len(sha256) != 64:
            raise CaseWorklistError(f"video queue result missing receipt/video/sha256 for {job['shot_id']}")
        path = Path(video).resolve()
        try:
            path.relative_to(self.workspace)
        except ValueError as exc:
            raise CaseWorklistError(f"video queue path escapes workspace for {job['shot_id']}") from exc
        if not path.is_file() or path.stat().st_size <= 0:
            raise CaseWorklistError(f"video queue artifact missing or empty for {job['shot_id']}")
        if self._sha256_file(path) != sha256:
            raise CaseWorklistError(f"video queue SHA256 mismatch for {job['shot_id']}")
        return {"status":"succeeded","group_execution_id":manifest["group_execution_id"],"job_id":job["queue_work_id"],"shot_id":job["shot_id"],"receipt":receipt,"workspace_mp4":video,"sha256":sha256,"plan":evidence.get("plan"),"durable_graph":evidence.get("durable_graph")}
