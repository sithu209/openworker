"""Cross-process mutation guard for :mod:`coworker.case_worklist`.

The JSON worklist is durable authority, while this module serializes mutations
from separate local processes that share one workspace.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from typing import Iterable, Iterator, Mapping

from .case_worklist import CaseStep, CaseWorklist, CaseWorklistError, CaseWorklistStore, StepStatus

_LOCK_NAME = "case-worklist.lock"
_ACTIVE_ACTION_KEY = "__openworker_active_action"
_ACTIVE_EXECUTION_KEY = "__openworker_active_execution"


class CaseWorklistRuntime:
    """Serialize worklist mutations and enforce one active action per case step."""

    def __init__(self, workspace_root: str | Path, *, lock_timeout: float = 30.0, stale_after: float = 180.0) -> None:
        self.store = CaseWorklistStore(workspace_root)
        self.lock_path = self.store.path.parent / _LOCK_NAME
        self.lock_timeout = float(lock_timeout)
        self.stale_after = float(stale_after)

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                self._remove_stale_lock_if_safe()
                if time.monotonic() >= deadline:
                    raise CaseWorklistError(f"case worklist mutation lock timeout: {self.lock_path}")
                time.sleep(0.05)
                continue
            try:
                payload = {"pid": os.getpid(), "created_unix": time.time()}
                os.write(fd, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
            finally:
                os.close(fd)
            break
        try:
            yield
        finally:
            try: self.lock_path.unlink()
            except FileNotFoundError: pass

    def _remove_stale_lock_if_safe(self) -> None:
        try: age = time.time() - self.lock_path.stat().st_mtime
        except FileNotFoundError: return
        if age <= self.stale_after: return
        try: self.lock_path.unlink()
        except FileNotFoundError: pass

    def load(self) -> CaseWorklist: return self.store.load()

    def ensure(self, manifest: CaseWorklist | None = None) -> CaseWorklist:
        with self.lock():
            if not self.store.path.is_file():
                if manifest is None: raise CaseWorklistError("manifest is required when creating a worklist")
                self.store.save(manifest); return manifest
            current = self.store.load()
            if manifest is None: return current
            reconciled, changed = self._reconcile_manifest(current, manifest)
            if changed:
                reconciled.revision = max(current.revision, manifest.revision) + 1
                reconciled.refresh(); self.store.save(reconciled)
            return reconciled

    @staticmethod
    def _reconcile_manifest(current: CaseWorklist, manifest: CaseWorklist) -> tuple[CaseWorklist, bool]:
        if current.case_id != manifest.case_id:
            raise CaseWorklistError(f"manifest reconcile case_id mismatch current={current.case_id!r} manifest={manifest.case_id!r}")
        current_by_id = {step.step_id: step for step in current.steps}; manifest_ids = {step.step_id for step in manifest.steps}; merged_steps: list[CaseStep] = []
        changed = current.assigned_host != manifest.assigned_host or current.schema_version != manifest.schema_version or current.parallel_policy != manifest.parallel_policy
        for declared in manifest.steps:
            existing = current_by_id.get(declared.step_id)
            if existing is None:
                merged_steps.append(CaseStep(**declared.__dict__)); changed = True; continue
            active_action = str(existing.evidence.get(_ACTIVE_ACTION_KEY, "") or "").strip()
            if existing.status == StepStatus.RUNNING and active_action and active_action not in declared.allowed_actions:
                raise CaseWorklistError(f"manifest reconcile cannot replace active action {active_action!r} on RUNNING step {existing.step_id!r}")
            declarative_changed = any((existing.title != declared.title, existing.kind != declared.kind, existing.dependencies != declared.dependencies, existing.allowed_actions != declared.allowed_actions, existing.acceptance != declared.acceptance, existing.repair_parent_step != declared.repair_parent_step, existing.allow_skip != declared.allow_skip))
            if declarative_changed: changed = True
            merged = CaseStep(step_id=declared.step_id,title=declared.title,kind=declared.kind,dependencies=list(declared.dependencies),allowed_actions=list(declared.allowed_actions),acceptance=list(declared.acceptance),status=existing.status,evidence=dict(existing.evidence),blocker=existing.blocker,repair_parent_step=declared.repair_parent_step,allow_skip=declared.allow_skip)
            if merged.status == StepStatus.PASSED:
                missing = [key for key in merged.acceptance if key not in merged.evidence]
                if missing:
                    merged.status = StepStatus.BLOCKED; merged.blocker = "manifest reconcile requires new acceptance evidence: " + ", ".join(missing); changed = True
            merged_steps.append(merged)
        extras = [step for step in current.steps if step.step_id not in manifest_ids]
        for extra in extras:
            if extra.kind == "repair": merged_steps.append(extra); continue
            if extra.status == StepStatus.RUNNING: raise CaseWorklistError(f"manifest reconcile found stale RUNNING non-repair step {extra.step_id!r}; stop it before upgrading manifest")
            preserved = CaseStep(**extra.__dict__)
            if preserved.status not in {StepStatus.PASSED, StepStatus.FAILED, StepStatus.SKIPPED}:
                preserved.status = StepStatus.SKIPPED; preserved.evidence = dict(preserved.evidence); preserved.evidence["skip_reason"] = "removed from latest static manifest during reconcile"; preserved.blocker = ""; changed = True
            merged_steps.append(preserved)
        reconciled = CaseWorklist(case_id=current.case_id,workspace_root=current.workspace_root,assigned_host=manifest.assigned_host,steps=merged_steps,schema_version=manifest.schema_version,revision=current.revision,parallel_policy=dict(manifest.parallel_policy))
        return reconciled, changed

    def add_repair(self, *, parent_step_id: str, step_id: str, title: str, allowed_actions: Iterable[str], acceptance: Iterable[str] = ()) -> CaseWorklist:
        with self.lock():
            worklist=self.store.load();worklist.add_repair(parent_step_id=parent_step_id,step_id=step_id,title=title,allowed_actions=allowed_actions,acceptance=acceptance);self.store.save(worklist);return worklist

    def start_action(self, step_id: str, action_id: str, *, execution_id: str) -> CaseWorklist:
        execution=execution_id.strip()
        if not execution: raise CaseWorklistError("execution_id is required for worklist action start")
        with self.lock():
            worklist=self.store.load();step=worklist.assert_action_allowed(step_id,action_id);active_action=str(step.evidence.get(_ACTIVE_ACTION_KEY,"") or "").strip();active_execution=str(step.evidence.get(_ACTIVE_EXECUTION_KEY,"") or "").strip()
            if active_action:
                if active_action==action_id and active_execution==execution:return worklist
                raise CaseWorklistError(f"case action concurrency blocked: step {step.step_id!r} already runs action {active_action!r} execution {active_execution!r}")
            worklist.start(step_id,action_id);step.evidence[_ACTIVE_ACTION_KEY]=action_id;step.evidence[_ACTIVE_EXECUTION_KEY]=execution;worklist.revision+=1;self.store.save(worklist);return worklist

    def resume_blocked_action(self, step_id: str, action_id: str, *, execution_id: str, recovery_evidence: Mapping[str, object]) -> CaseWorklist:
        """Restore one exact BLOCKED action only after the caller supplies proof.

        This primitive intentionally does not discover or infer recovery safety.
        The caller must first prove the durable external execution identity (for
        Case 0005, every manifest child must already exist in :8848 with matching
        host/capability). The supplied proof is persisted before RUNNING resumes.
        """
        action=action_id.strip();execution=execution_id.strip()
        if not action or not execution: raise CaseWorklistError("action_id and execution_id are required for blocked action resume")
        if not recovery_evidence: raise CaseWorklistError("blocked action resume requires durable recovery evidence")
        with self.lock():
            worklist=self.store.load();step=worklist.step(step_id)
            if step.status != StepStatus.BLOCKED: raise CaseWorklistError(f"blocked action resume requires BLOCKED step, got {step.status.value}")
            if action not in step.allowed_actions: raise CaseWorklistError(f"blocked action {action!r} is not allowed for step {step_id!r}")
            if step.evidence.get(_ACTIVE_ACTION_KEY) or step.evidence.get(_ACTIVE_EXECUTION_KEY): raise CaseWorklistError("blocked action resume requires no active ownership")
            step.evidence["__openworker_recovery_evidence"] = dict(recovery_evidence)
            step.evidence[_ACTIVE_ACTION_KEY]=action;step.evidence[_ACTIVE_EXECUTION_KEY]=execution;step.status=StepStatus.RUNNING;step.blocker="";worklist.revision+=1;self.store.save(worklist);return worklist

    def retry_stale_active(self, step_id: str, *, execution_id: str) -> CaseWorklist:
        expected=execution_id.strip()
        if not expected: raise CaseWorklistError("execution_id is required for stale active retry")
        with self.lock():
            worklist=self.store.load();step=worklist.step(step_id);active=str(step.evidence.get(_ACTIVE_EXECUTION_KEY,"") or "").strip()
            if step.status != StepStatus.RUNNING: raise CaseWorklistError(f"stale active retry requires RUNNING step, got {step.status.value}")
            if active != expected: raise CaseWorklistError(f"stale active retry ownership mismatch for step {step.step_id!r}: expected execution={expected!r} actual={active!r}")
            step.evidence.pop(_ACTIVE_ACTION_KEY,None);step.evidence.pop(_ACTIVE_EXECUTION_KEY,None);step.status=StepStatus.READY;step.blocker="";worklist.revision+=1;self.store.save(worklist);return worklist

    def complete_action(self, step_id: str, action_id: str, *, execution_id: str) -> CaseWorklist:
        with self.lock():
            worklist=self.store.load();step=worklist.step(step_id);self._assert_active(step,action_id,execution_id);step.evidence.pop(_ACTIVE_ACTION_KEY,None);step.evidence.pop(_ACTIVE_EXECUTION_KEY,None);worklist.revision+=1;self.store.save(worklist);return worklist

    def accept_action_evidence(self, step_id: str, action_id: str, *, execution_id: str, evidence: Mapping[str, object]) -> CaseWorklist:
        if not evidence: raise CaseWorklistError("accepted action evidence cannot be empty")
        with self.lock():
            worklist=self.store.load();step=worklist.step(step_id);self._assert_active(step,action_id,execution_id)
            for key,value in evidence.items(): worklist.record_evidence(step_id,key,value)
            step.evidence.pop(_ACTIVE_ACTION_KEY,None);step.evidence.pop(_ACTIVE_EXECUTION_KEY,None);worklist.revision+=1;worklist.pass_step(step_id);self.store.save(worklist);return worklist

    def record(self, step_id: str, key: str, value: object) -> CaseWorklist:
        with self.lock(): worklist=self.store.load();worklist.record_evidence(step_id,key,value);self.store.save(worklist);return worklist

    def pass_step(self, step_id: str) -> CaseWorklist:
        with self.lock():
            worklist=self.store.load();step=worklist.step(step_id)
            if step.evidence.get(_ACTIVE_ACTION_KEY): raise CaseWorklistError(f"step {step.step_id!r} cannot pass while action {step.evidence[_ACTIVE_ACTION_KEY]!r} is active")
            worklist.pass_step(step_id);self.store.save(worklist);return worklist

    def block_active(self, step_id: str, reason: str) -> CaseWorklist:
        with self.lock():
            worklist=self.store.load();step=worklist.step(step_id);step.evidence.pop(_ACTIVE_ACTION_KEY,None);step.evidence.pop(_ACTIVE_EXECUTION_KEY,None)
            if step.status in {StepStatus.RUNNING,StepStatus.READY}:worklist.block(step_id,reason)
            elif step.status != StepStatus.BLOCKED:return worklist
            self.store.save(worklist);return worklist

    @staticmethod
    def _assert_active(step, action_id: str, execution_id: str) -> None:
        action=str(step.evidence.get(_ACTIVE_ACTION_KEY,"") or "").strip();execution=str(step.evidence.get(_ACTIVE_EXECUTION_KEY,"") or "").strip()
        if action != action_id.strip() or execution != execution_id.strip(): raise CaseWorklistError(f"active action ownership mismatch for step {step.step_id!r}: expected action={action!r} execution={execution!r}")
