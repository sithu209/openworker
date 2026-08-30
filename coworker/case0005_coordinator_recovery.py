"""Recovery for Case 0005 queue-owned fanout coordinators.

The durable business queue is go-tool :8848. A missing/failed OpenWorker
coordinator must never cause business children to be submitted again, and
coordinator recovery must never erase a real business-child failure.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .case_worklist import StepStatus


class Case0005CoordinatorRecoveryMixin:
    def _prove_all_queue_children(self, manifest: Mapping[str, Any]) -> dict[str, Any] | None:
        jobs = manifest.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            return None
        expected_host = str(manifest.get("assigned_host", "")).strip()
        expected_capability = str(manifest.get("action_id", "")).strip()
        proven: list[dict[str, Any]] = []
        for raw in jobs:
            if not isinstance(raw, Mapping): return None
            work_id = str(raw.get("queue_work_id", "")).strip()
            if not work_id: return None
            try: item = self._queue_get(work_id)
            except Exception: return None
            if str(item.get("work_id", "")).strip() != work_id: return None
            if str(item.get("assigned_host", "")).strip().lower() != expected_host.lower(): return None
            if str(item.get("capability_id", "")).strip() != expected_capability: return None
            status = str(item.get("status", "")).strip().lower()
            # A failed business work is not a coordinator outage and must stay
            # BLOCKED for normal repair/retry handling.
            if status not in {"pending", "claimed", "completed"}: return None
            proven.append({"work_id": work_id, "status": status, "attempts": item.get("attempts", 0)})
        return {
            "queue_authority": "go-tool-runtime:8848",
            "all_manifest_children_durable": True,
            "no_business_child_failed": True,
            "child_count": len(proven),
            "children": proven,
            "business_children_resubmitted": False,
        }

    @staticmethod
    def _is_coordinator_submit_blocker(blocker: str) -> bool:
        text = str(blocker or "").strip().lower()
        return text.startswith("direct local queue image fanout submit failed:") or text.startswith("direct local queue video fanout submit failed:")

    def _resume_queue_owned_coordinators(self) -> list[dict[str, Any]]:
        worklist = self.runtime.load()
        fanout_root = self.workspace / ".openworker" / "fanout"
        if not fanout_root.is_dir(): return []
        recovered: list[dict[str, Any]] = []
        for manifest_path in sorted(fanout_root.glob("*/fanout-manifest.json")):
            try: manifest = self._load_json(manifest_path)
            except Exception as exc:
                self._append_ledger("queue_coordinator_manifest_invalid", manifest_path=str(manifest_path), error=str(exc)); continue
            if not isinstance(manifest, Mapping) or not bool(manifest.get("queue_owns_all_children")): continue
            step_id=str(manifest.get("step_id","")).strip();group_id=str(manifest.get("group_execution_id","")).strip();action=str(manifest.get("action_id","")).strip()
            if not step_id or not group_id or not action: continue
            try: step=worklist.step(step_id)
            except Exception: continue

            if step.status == StepStatus.BLOCKED:
                if not self._is_coordinator_submit_blocker(step.blocker):
                    self._append_ledger("queue_fanout_blocked_not_resumable",step_id=step_id,group_execution_id=group_id,blocker=step.blocker,reason="blocker is not a coordinator-submit outage")
                    continue
                proof=self._prove_all_queue_children(manifest)
                if proof is None:
                    self._append_ledger("queue_fanout_blocked_not_resumable",step_id=step_id,group_execution_id=group_id,blocker=step.blocker,reason="not every manifest child is durable and non-failed in :8848 with matching identity")
                    continue
                self.runtime.resume_blocked_action(step_id,action,execution_id=group_id,recovery_evidence=proof)
                entry={"step_id":step_id,"group_execution_id":group_id,"action":"resumed_blocked_from_complete_queue_proof","proof":proof};recovered.append(entry)
                self._append_ledger("queue_fanout_resumed",**entry,execution_route="local_supervisor")
                worklist=self.runtime.load();step=worklist.step(step_id)

            if step.status != StepStatus.RUNNING: continue
            active=str(step.evidence.get("__openworker_active_execution","") or "").strip()
            if active != group_id: continue
            kind="video" if action=="comfyx.production.video.real" else "image";timeout=14400 if kind=="video" else 5400;coordinator_id=f"{group_id}--queue-coordinator"
            try: state=self.node.job_status(coordinator_id)
            except Exception: state=None
            status=str((state or {}).get("status","")).strip().lower()
            if state is None:
                payload=self._coordinator_payload(worklist,group_id=group_id,kind=kind,manifest_path=Path(manifest_path),timeout_sec=timeout);ack=self.node.submit(payload)
                if bool(ack.get("accepted")):
                    entry={"step_id":step_id,"group_execution_id":group_id,"coordinator_id":coordinator_id,"action":"submitted_missing","ack":ack};recovered.append(entry);self._append_ledger("queue_coordinator_recovered",**entry,queue_authority="go-tool-runtime:8848",business_children_resubmitted=False)
                continue
            if status in {"failed","cancelled","canceled"}:
                result=self.node.retry(coordinator_id);entry={"step_id":step_id,"group_execution_id":group_id,"coordinator_id":coordinator_id,"action":"retried_terminal","previous_status":status,"result":result};recovered.append(entry);self._append_ledger("queue_coordinator_recovered",**entry,queue_authority="go-tool-runtime:8848",business_children_resubmitted=False);continue
            self._append_ledger("queue_coordinator_observed",step_id=step_id,group_execution_id=group_id,coordinator_id=coordinator_id,coordinator_status=status or "unknown",queue_authority="go-tool-runtime:8848",business_children_resubmitted=False)
        return recovered
