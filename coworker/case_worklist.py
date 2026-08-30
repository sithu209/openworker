"""Durable, fail-closed case worklist for long-running OpenWorker cases.

The worklist is the job-scoped authority for execution order and DAG readiness.
It does not replace product lifecycle, WorkLedger, go-tool-runtime, or case docs.
Multiple independent READY/RUNNING work steps are allowed; process scheduling
remains the responsibility of the OpenWorker Go execution kernel.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


class CaseWorklistError(RuntimeError):
    """Raised when a case attempts to drift outside its declared worklist."""


class StepStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


_TERMINAL_OK = {StepStatus.PASSED, StepStatus.SKIPPED}


@dataclass
class CaseStep:
    step_id: str
    title: str
    kind: str = "work"
    dependencies: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    evidence: dict[str, Any] = field(default_factory=dict)
    blocker: str = ""
    repair_parent_step: str = ""
    allow_skip: bool = False

    def validate(self) -> None:
        self.step_id = self.step_id.strip()
        self.title = self.title.strip()
        self.kind = self.kind.strip() or "work"
        self.dependencies = _unique_nonempty(self.dependencies, "dependency")
        self.allowed_actions = _unique_nonempty(self.allowed_actions, "allowed action")
        self.acceptance = _unique_nonempty(self.acceptance, "acceptance key")
        self.repair_parent_step = self.repair_parent_step.strip()
        if not self.step_id:
            raise CaseWorklistError("step_id is required")
        if not self.title:
            raise CaseWorklistError(f"step {self.step_id!r} title is required")
        if self.step_id in self.dependencies:
            raise CaseWorklistError(f"step {self.step_id!r} cannot depend on itself")
        if self.kind == "repair" and not self.repair_parent_step:
            raise CaseWorklistError(f"repair step {self.step_id!r} requires repair_parent_step")
        if self.kind != "repair" and self.repair_parent_step:
            raise CaseWorklistError(f"non-repair step {self.step_id!r} cannot set repair_parent_step")


@dataclass
class CaseWorklist:
    case_id: str
    workspace_root: str
    assigned_host: str
    steps: list[CaseStep]
    schema_version: str = "openworker-case-worklist/v1"
    revision: int = 1
    parallel_policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.case_id = self.case_id.strip()
        self.workspace_root = str(Path(self.workspace_root).expanduser().resolve())
        self.assigned_host = self.assigned_host.strip()
        if not isinstance(self.parallel_policy, dict):
            raise CaseWorklistError("parallel_policy must be an object")
        if not self.case_id:
            raise CaseWorklistError("case_id is required")
        if not self.assigned_host:
            raise CaseWorklistError("assigned_host is required")
        if not self.steps:
            raise CaseWorklistError("at least one case step is required")
        self._validate_graph()
        self.refresh()

    def _validate_graph(self) -> None:
        seen: set[str] = set()
        by_id: dict[str, CaseStep] = {}
        for step in self.steps:
            step.validate()
            if step.step_id in seen:
                raise CaseWorklistError(f"duplicate step_id {step.step_id!r}")
            seen.add(step.step_id)
            by_id[step.step_id] = step
        for step in self.steps:
            for dep in step.dependencies:
                if dep not in by_id:
                    raise CaseWorklistError(f"step {step.step_id!r} depends on unknown step {dep!r}")
            if step.repair_parent_step:
                if step.repair_parent_step not in by_id:
                    raise CaseWorklistError(
                        f"repair step {step.step_id!r} has unknown parent {step.repair_parent_step!r}"
                    )
                if step.repair_parent_step == step.step_id:
                    raise CaseWorklistError(f"repair step {step.step_id!r} cannot repair itself")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                raise CaseWorklistError(f"dependency cycle detected at {step_id!r}")
            visiting.add(step_id)
            for dep in by_id[step_id].dependencies:
                visit(dep)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in by_id:
            visit(step_id)

    def step(self, step_id: str) -> CaseStep:
        wanted = step_id.strip()
        for step in self.steps:
            if step.step_id == wanted:
                return step
        raise CaseWorklistError(f"unknown step_id {wanted!r}")

    def _dependencies_satisfied(self, step: CaseStep) -> bool:
        return all(self.step(dep).status in _TERMINAL_OK for dep in step.dependencies)

    def _active_repairs(self) -> list[CaseStep]:
        return [
            step
            for step in self.steps
            if step.kind == "repair" and step.status not in _TERMINAL_OK
        ]

    def refresh(self) -> None:
        """Recompute READY/PENDING without changing RUNNING/BLOCKED/terminal states.

        Repairs retain fail-closed precedence: while an unfinished repair exists,
        no new non-repair work becomes READY. Already RUNNING jobs are not
        rewritten here; their process lifecycle is authoritative in OpenWorker.
        """
        active_repairs = self._active_repairs()
        active_repair_ids = {step.step_id for step in active_repairs}
        blocked_parents = {step.repair_parent_step for step in active_repairs}

        for step in self.steps:
            if step.status in {
                StepStatus.RUNNING,
                StepStatus.BLOCKED,
                StepStatus.PASSED,
                StepStatus.FAILED,
                StepStatus.SKIPPED,
            }:
                continue
            if step.step_id in blocked_parents:
                step.status = StepStatus.PENDING
                continue
            if active_repair_ids and step.kind != "repair":
                step.status = StepStatus.PENDING
                continue
            step.status = StepStatus.READY if self._dependencies_satisfied(step) else StepStatus.PENDING

    def ready_steps(self) -> list[CaseStep]:
        """Return the complete executable DAG frontier in manifest order.

        When repairs are READY, only repair steps are returned. Otherwise all
        independent READY work/approval steps are returned so the local
        controller can fan them out concurrently without creating a scheduler.
        """
        self.refresh()
        repairs = [step for step in self.steps if step.kind == "repair" and step.status == StepStatus.READY]
        if repairs:
            return repairs
        return [step for step in self.steps if step.kind != "repair" and step.status == StepStatus.READY]

    def running_steps(self) -> list[CaseStep]:
        """Return all currently RUNNING DAG nodes in manifest order."""
        return [step for step in self.steps if step.status == StepStatus.RUNNING]

    def next_step(self) -> CaseStep | None:
        """Compatibility view returning one representative current/next step.

        New controllers must use :meth:`ready_steps` / :meth:`running_steps`.
        Older clients still receive the first RUNNING step, then first READY
        repair, then first READY work step in manifest order.
        """
        self.refresh()
        running = self.running_steps()
        if running:
            return running[0]
        ready = self.ready_steps()
        return ready[0] if ready else None

    def assert_action_allowed(self, step_id: str, action_id: str) -> CaseStep:
        """Validate an action against the current DAG frontier.

        Unlike the legacy single-canonical-step rule, any READY frontier node
        may start independently, and an already RUNNING node may continue its
        exact action ownership lifecycle.
        """
        self.refresh()
        step = self.step(step_id)
        action = action_id.strip()
        if not action:
            raise CaseWorklistError("action_id is required")
        if action not in step.allowed_actions:
            raise CaseWorklistError(
                f"action {action!r} is not allowed for step {step.step_id!r}"
            )
        if not self._dependencies_satisfied(step):
            raise CaseWorklistError(f"dependencies are not satisfied for step {step.step_id!r}")
        if step.status not in {StepStatus.READY, StepStatus.RUNNING}:
            frontier = [item.step_id for item in self.ready_steps()]
            raise CaseWorklistError(
                f"case drift blocked: step {step.step_id!r} is {step.status.value}; "
                f"ready frontier={frontier!r}"
            )
        if step.status == StepStatus.READY:
            frontier = {item.step_id for item in self.ready_steps()}
            if step.step_id not in frontier:
                raise CaseWorklistError(
                    f"case drift blocked: step {step.step_id!r} is outside ready frontier"
                )
        return step

    def start(self, step_id: str, action_id: str) -> CaseStep:
        step = self.assert_action_allowed(step_id, action_id)
        if step.status == StepStatus.READY:
            step.status = StepStatus.RUNNING
            step.blocker = ""
            self.revision += 1
        return step

    def block(self, step_id: str, reason: str) -> CaseStep:
        step = self.step(step_id)
        if step.status not in {StepStatus.RUNNING, StepStatus.READY}:
            raise CaseWorklistError(f"step {step.step_id!r} cannot be blocked from {step.status.value}")
        normalized = reason.strip()
        if not normalized:
            raise CaseWorklistError("blocker reason is required")
        step.status = StepStatus.BLOCKED
        step.blocker = normalized
        self.revision += 1
        return step

    def add_repair(
        self,
        *,
        parent_step_id: str,
        step_id: str,
        title: str,
        allowed_actions: Iterable[str],
        acceptance: Iterable[str] = (),
    ) -> CaseStep:
        parent = self.step(parent_step_id)
        if parent.status != StepStatus.BLOCKED:
            raise CaseWorklistError(
                f"repair may only be added to a BLOCKED parent; {parent.step_id!r} is {parent.status.value}"
            )
        repair = CaseStep(
            step_id=step_id,
            title=title,
            kind="repair",
            dependencies=list(parent.dependencies),
            allowed_actions=list(allowed_actions),
            acceptance=list(acceptance),
            repair_parent_step=parent.step_id,
        )
        repair.validate()
        if any(existing.step_id == repair.step_id for existing in self.steps):
            raise CaseWorklistError(f"duplicate step_id {repair.step_id!r}")
        parent_index = self.steps.index(parent)
        insert_at = parent_index + 1
        while insert_at < len(self.steps) and self.steps[insert_at].repair_parent_step == parent.step_id:
            insert_at += 1
        self.steps.insert(insert_at, repair)
        self._validate_graph()
        self.revision += 1
        self.refresh()
        return repair

    def record_evidence(self, step_id: str, key: str, value: Any) -> CaseStep:
        step = self.step(step_id)
        if step.status not in {StepStatus.RUNNING, StepStatus.BLOCKED}:
            raise CaseWorklistError(
                f"step {step.step_id!r} cannot record evidence from {step.status.value}"
            )
        normalized = key.strip()
        if not normalized:
            raise CaseWorklistError("evidence key is required")
        if value is None or value == "":
            raise CaseWorklistError(f"evidence {normalized!r} cannot be empty")
        step.evidence[normalized] = value
        self.revision += 1
        return step

    def pass_step(self, step_id: str) -> CaseStep:
        step = self.step(step_id)
        if step.status not in {StepStatus.RUNNING, StepStatus.BLOCKED}:
            raise CaseWorklistError(f"step {step.step_id!r} cannot pass from {step.status.value}")
        missing = [key for key in step.acceptance if key not in step.evidence]
        if missing:
            raise CaseWorklistError(
                f"step {step.step_id!r} missing acceptance evidence: {', '.join(missing)}"
            )
        step.status = StepStatus.PASSED
        step.blocker = ""
        if step.kind == "repair":
            parent = self.step(step.repair_parent_step)
            if parent.status == StepStatus.BLOCKED:
                parent.status = StepStatus.PENDING
                parent.blocker = ""
        self.revision += 1
        self.refresh()
        return step

    def fail(self, step_id: str, reason: str) -> CaseStep:
        step = self.step(step_id)
        normalized = reason.strip()
        if not normalized:
            raise CaseWorklistError("failure reason is required")
        step.status = StepStatus.FAILED
        step.blocker = normalized
        self.revision += 1
        return step

    def skip(self, step_id: str, reason: str) -> CaseStep:
        step = self.step(step_id)
        if not step.allow_skip:
            raise CaseWorklistError(f"step {step.step_id!r} does not allow SKIPPED")
        if not reason.strip():
            raise CaseWorklistError("skip reason is required")
        step.status = StepStatus.SKIPPED
        step.evidence["skip_reason"] = reason.strip()
        self.revision += 1
        self.refresh()
        return step

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for raw in payload["steps"]:
            raw["status"] = raw["status"].value if isinstance(raw["status"], StepStatus) else raw["status"]
        canonical = self.next_step()
        payload["canonical_next_step_id"] = canonical.step_id if canonical else None
        payload["ready_step_ids"] = [step.step_id for step in self.ready_steps()]
        payload["running_step_ids"] = [step.step_id for step in self.running_steps()]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CaseWorklist":
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            raise CaseWorklistError("steps must be a list")
        steps: list[CaseStep] = []
        for raw in raw_steps:
            if not isinstance(raw, Mapping):
                raise CaseWorklistError("each step must be an object")
            data = dict(raw)
            data.pop("canonical_next_step_id", None)
            data.pop("ready_step_ids", None)
            data.pop("running_step_ids", None)
            try:
                data["status"] = StepStatus(str(data.get("status", StepStatus.PENDING.value)))
            except ValueError as exc:
                raise CaseWorklistError(f"invalid step status {data.get('status')!r}") from exc
            steps.append(CaseStep(**data))
        parallel_policy = payload.get("parallel_policy", {})
        if parallel_policy is None:
            parallel_policy = {}
        if not isinstance(parallel_policy, Mapping):
            raise CaseWorklistError("parallel_policy must be an object")
        return cls(
            case_id=str(payload.get("case_id", "")),
            workspace_root=str(payload.get("workspace_root", "")),
            assigned_host=str(payload.get("assigned_host", "")),
            steps=steps,
            schema_version=str(payload.get("schema_version", "openworker-case-worklist/v1")),
            revision=int(payload.get("revision", 1)),
            parallel_policy=dict(parallel_policy),
        )


class CaseWorklistStore:
    """Atomic JSON persistence under ``<workspace>/.openworker``."""

    FILENAME = "case-worklist.json"

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.path = self.workspace_root / ".openworker" / self.FILENAME

    def save(self, worklist: CaseWorklist) -> Path:
        if Path(worklist.workspace_root).resolve() != self.workspace_root:
            raise CaseWorklistError("worklist workspace_root does not match store workspace")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(worklist.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, self.path)
        return self.path

    def load(self) -> CaseWorklist:
        if not self.path.is_file():
            raise CaseWorklistError(f"case worklist not found: {self.path}")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CaseWorklistError(f"cannot read case worklist: {self.path}") from exc
        if not isinstance(payload, Mapping):
            raise CaseWorklistError("case worklist root must be an object")
        worklist = CaseWorklist.from_dict(payload)
        if Path(worklist.workspace_root).resolve() != self.workspace_root:
            raise CaseWorklistError("persisted worklist workspace_root does not match store workspace")
        return worklist


def _unique_nonempty(values: Iterable[str], label: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            raise CaseWorklistError(f"{label} cannot be empty")
        if value in seen:
            raise CaseWorklistError(f"duplicate {label} {value!r}")
        seen.add(value)
        result.append(value)
    return result
