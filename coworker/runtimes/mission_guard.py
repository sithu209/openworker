"""Persistent mission contract and drift guard for long-running OpenWorker jobs.

The guard is intentionally generic: it does not own domain workflows.  It keeps
one mission anchored to the fixed OpenWorker workspace/job binding and blocks
side-effecting actions that violate host/workspace/job invariants, owner
boundaries, capability allowlists, or retry budgets.  Uncertain/failing actions
are routed back to go-tool-runtime for information-only re-query instead of
letting the model guess a new route.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .job_binding import JobBinding, JobBindingStore
from .tool_runtime_bootstrap import ToolRuntimeBootstrapClient, ToolRuntimeQuery


class MissionGuardError(RuntimeError):
    """Raised for invalid or conflicting persisted mission state."""


class DriftDecision(str, Enum):
    ALLOW = "allow"
    REQUERY = "requery"
    BLOCK = "block"


@dataclass(frozen=True)
class MissionContract:
    schema_version: str
    mission_id: str
    user_goal: str
    project_id: str
    job_id: str
    assigned_host: str
    workspace_root: str
    success_criteria: tuple[str, ...] = ()
    expected_deliverables: tuple[str, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    owner_boundaries: dict[str, str] = field(default_factory=dict)
    prohibited_actions: tuple[str, ...] = ()
    authoritative_sources: tuple[str, ...] = ()
    max_retries_per_failure: int = 2


@dataclass(frozen=True)
class MissionAction:
    name: str
    capability_id: str = ""
    owner: str = ""
    project_id: str = ""
    job_id: str = ""
    assigned_host: str = ""
    workspace_root: str = ""
    side_effecting: bool = False
    uncertain: bool = False
    failure_class: str = ""
    retry_key: str = ""


@dataclass(frozen=True)
class DriftAssessment:
    decision: DriftDecision
    reasons: tuple[str, ...] = ()
    drift_score: int = 0
    should_requery: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision is DriftDecision.ALLOW


@dataclass(frozen=True)
class MissionCheckpoint:
    schema_version: str
    mission_id: str
    sequence: int
    stage: str
    current_goal: str
    current_owner: str = ""
    current_capability: str = ""
    latest_evidence: tuple[str, ...] = ()
    completed_criteria: tuple[str, ...] = ()
    unresolved_blockers: tuple[str, ...] = ()
    next_intended_action: str = ""
    retry_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FailureGuidanceRequest:
    mission_id: str
    stage: str
    failure_class: str
    error: str
    owner: str
    capability_id: str
    evidence: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)


class MissionStore:
    """Durable `.openworker` mission contract/checkpoint store."""

    def __init__(self, workspace: str | os.PathLike[str]) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.root = self.workspace / ".openworker"
        self.contract_path = self.root / "mission-contract.json"
        self.checkpoint_path = self.root / "mission-checkpoint.json"

    @staticmethod
    def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def create_contract(
        self,
        *,
        mission_id: str,
        user_goal: str,
        binding: JobBinding,
        success_criteria: Iterable[str] = (),
        expected_deliverables: Iterable[str] = (),
        allowed_capabilities: Iterable[str] = (),
        owner_boundaries: dict[str, str] | None = None,
        prohibited_actions: Iterable[str] = (),
        authoritative_sources: Iterable[str] = (),
        max_retries_per_failure: int = 2,
    ) -> MissionContract:
        if self.contract_path.exists():
            raise MissionGuardError(f"mission contract already exists: {self.contract_path}")
        normalized_goal = str(user_goal or "").strip()
        normalized_id = str(mission_id or "").strip()
        if not normalized_id or not normalized_goal:
            raise MissionGuardError("mission_id and user_goal are required")
        if max_retries_per_failure < 0:
            raise MissionGuardError("max_retries_per_failure must be >= 0")
        contract = MissionContract(
            schema_version="openworker.mission-contract.v1",
            mission_id=normalized_id,
            user_goal=normalized_goal,
            project_id=binding.project_id,
            job_id=binding.job_id,
            assigned_host=binding.assigned_host,
            workspace_root=binding.workspace_root,
            success_criteria=tuple(str(v).strip() for v in success_criteria if str(v).strip()),
            expected_deliverables=tuple(str(v).strip() for v in expected_deliverables if str(v).strip()),
            allowed_capabilities=tuple(str(v).strip() for v in allowed_capabilities if str(v).strip()),
            owner_boundaries=dict(owner_boundaries or {}),
            prohibited_actions=tuple(str(v).strip() for v in prohibited_actions if str(v).strip()),
            authoritative_sources=tuple(str(v).strip() for v in authoritative_sources if str(v).strip()),
            max_retries_per_failure=max_retries_per_failure,
        )
        self._write_atomic(self.contract_path, asdict(contract))
        return contract

    def load_contract(self) -> MissionContract | None:
        if not self.contract_path.exists():
            return None
        try:
            raw = json.loads(self.contract_path.read_text(encoding="utf-8"))
            raw["success_criteria"] = tuple(raw.get("success_criteria", ()))
            raw["expected_deliverables"] = tuple(raw.get("expected_deliverables", ()))
            raw["allowed_capabilities"] = tuple(raw.get("allowed_capabilities", ()))
            raw["prohibited_actions"] = tuple(raw.get("prohibited_actions", ()))
            raw["authoritative_sources"] = tuple(raw.get("authoritative_sources", ()))
            contract = MissionContract(**raw)
        except (OSError, ValueError, TypeError) as exc:
            raise MissionGuardError(f"invalid mission contract: {exc}") from exc
        if contract.schema_version != "openworker.mission-contract.v1":
            raise MissionGuardError(f"unsupported mission contract schema: {contract.schema_version}")
        return contract

    def load_checkpoint(self) -> MissionCheckpoint | None:
        if not self.checkpoint_path.exists():
            return None
        try:
            raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            raw["latest_evidence"] = tuple(raw.get("latest_evidence", ()))
            raw["completed_criteria"] = tuple(raw.get("completed_criteria", ()))
            raw["unresolved_blockers"] = tuple(raw.get("unresolved_blockers", ()))
            checkpoint = MissionCheckpoint(**raw)
        except (OSError, ValueError, TypeError) as exc:
            raise MissionGuardError(f"invalid mission checkpoint: {exc}") from exc
        if checkpoint.schema_version != "openworker.mission-checkpoint.v1":
            raise MissionGuardError(f"unsupported mission checkpoint schema: {checkpoint.schema_version}")
        return checkpoint

    def checkpoint(
        self,
        contract: MissionContract,
        *,
        stage: str,
        current_goal: str,
        current_owner: str = "",
        current_capability: str = "",
        latest_evidence: Iterable[str] = (),
        completed_criteria: Iterable[str] = (),
        unresolved_blockers: Iterable[str] = (),
        next_intended_action: str = "",
        retry_counts: dict[str, int] | None = None,
    ) -> MissionCheckpoint:
        previous = self.load_checkpoint()
        sequence = 1 if previous is None else previous.sequence + 1
        counts = dict(retry_counts if retry_counts is not None else (previous.retry_counts if previous else {}))
        checkpoint = MissionCheckpoint(
            schema_version="openworker.mission-checkpoint.v1",
            mission_id=contract.mission_id,
            sequence=sequence,
            stage=str(stage or "").strip(),
            current_goal=str(current_goal or "").strip(),
            current_owner=str(current_owner or "").strip(),
            current_capability=str(current_capability or "").strip(),
            latest_evidence=tuple(str(v).strip() for v in latest_evidence if str(v).strip()),
            completed_criteria=tuple(str(v).strip() for v in completed_criteria if str(v).strip()),
            unresolved_blockers=tuple(str(v).strip() for v in unresolved_blockers if str(v).strip()),
            next_intended_action=str(next_intended_action or "").strip(),
            retry_counts=counts,
        )
        self._write_atomic(self.checkpoint_path, asdict(checkpoint))
        return checkpoint


class MissionDriftGuard:
    """Fail-closed policy gate for proposed long-job actions."""

    def __init__(self, workspace: str | os.PathLike[str], contract: MissionContract) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.contract = contract

    @classmethod
    def from_workspace(cls, workspace: str | os.PathLike[str]) -> "MissionDriftGuard":
        store = MissionStore(workspace)
        contract = store.load_contract()
        if contract is None:
            raise MissionGuardError("mission contract is required before guarded execution")
        return cls(workspace, contract)

    def _binding_reasons(self) -> list[str]:
        reasons: list[str] = []
        binding = JobBindingStore(self.workspace).load()
        if binding is None:
            return ["fixed job binding is missing"]
        pairs = (
            ("project_id", binding.project_id, self.contract.project_id),
            ("job_id", binding.job_id, self.contract.job_id),
            ("assigned_host", binding.assigned_host.casefold(), self.contract.assigned_host.casefold()),
            ("workspace_root", os.path.normcase(binding.workspace_root), os.path.normcase(self.contract.workspace_root)),
        )
        for label, actual, expected in pairs:
            if actual != expected:
                reasons.append(f"mission {label} changed: expected {expected}, got {actual}")
        return reasons

    def assess(self, action: MissionAction, *, retry_count: int = 0) -> DriftAssessment:
        reasons = self._binding_reasons()
        hard_block = bool(reasons)

        def conflict(label: str, actual: str, expected: str) -> None:
            nonlocal hard_block
            if actual and actual != expected:
                reasons.append(f"{label} drift: expected {expected}, got {actual}")
                hard_block = True

        conflict("project_id", action.project_id, self.contract.project_id)
        conflict("job_id", action.job_id, self.contract.job_id)
        if action.assigned_host and action.assigned_host.casefold() != self.contract.assigned_host.casefold():
            reasons.append(
                f"host drift: mission is fixed to {self.contract.assigned_host}, action requests {action.assigned_host}"
            )
            hard_block = True
        if action.workspace_root:
            actual = os.path.normcase(str(Path(action.workspace_root).expanduser().resolve()))
            expected = os.path.normcase(str(Path(self.contract.workspace_root).expanduser().resolve()))
            if actual != expected:
                reasons.append(f"workspace drift: expected {self.contract.workspace_root}, got {action.workspace_root}")
                hard_block = True

        normalized_name = action.name.strip().casefold()
        for prohibited in self.contract.prohibited_actions:
            if prohibited.casefold() in normalized_name:
                reasons.append(f"prohibited mission action: {prohibited}")
                hard_block = True

        if action.side_effecting and self.contract.allowed_capabilities:
            if not action.capability_id or action.capability_id not in self.contract.allowed_capabilities:
                reasons.append(f"capability is outside mission allowlist: {action.capability_id or '<missing>'}")
                hard_block = True

        if action.capability_id and action.capability_id in self.contract.owner_boundaries:
            expected_owner = self.contract.owner_boundaries[action.capability_id]
            if action.owner and action.owner != expected_owner:
                reasons.append(
                    f"owner boundary drift for {action.capability_id}: expected {expected_owner}, got {action.owner}"
                )
                hard_block = True

        if action.retry_key and retry_count >= self.contract.max_retries_per_failure:
            reasons.append(
                f"retry budget exhausted for {action.retry_key}: {retry_count}/{self.contract.max_retries_per_failure}"
            )
            hard_block = True

        if hard_block:
            return DriftAssessment(
                decision=DriftDecision.BLOCK,
                reasons=tuple(reasons),
                drift_score=min(100, 70 + 5 * len(reasons)),
                should_requery=False,
            )

        if action.uncertain or action.failure_class:
            reasons.append("tool/parameter/success uncertainty requires information-authority re-query")
            return DriftAssessment(
                decision=DriftDecision.REQUERY,
                reasons=tuple(reasons),
                drift_score=45,
                should_requery=True,
            )

        return DriftAssessment(decision=DriftDecision.ALLOW, reasons=tuple(reasons), drift_score=0)

    def require_allowed(self, action: MissionAction, *, retry_count: int = 0) -> None:
        assessment = self.assess(action, retry_count=retry_count)
        if assessment.decision is DriftDecision.BLOCK:
            raise MissionGuardError("; ".join(assessment.reasons) or "mission drift blocked")
        if assessment.decision is DriftDecision.REQUERY:
            raise MissionGuardError("mission action requires go-tool-runtime re-query before execution")

    def requery_failure(
        self,
        client: ToolRuntimeBootstrapClient,
        request: FailureGuidanceRequest,
        *,
        project: str,
        session_id: str,
    ) -> ToolRuntimeQuery:
        question = (
            "OpenWorker long-job failure/uncertainty re-query. "
            f"mission_id={request.mission_id}; stage={request.stage}; failure_class={request.failure_class}; "
            f"owner={request.owner}; capability_id={request.capability_id}; error={request.error}; "
            f"parameters={json.dumps(request.parameters, ensure_ascii=False, sort_keys=True)}; "
            f"evidence={json.dumps(list(request.evidence), ensure_ascii=False)}. "
            "Return the authoritative owning layer, capability/contract constraints, allowed next actions, "
            "prohibited actions, retry policy, and escalation reason. Do not execute or mutate anything."
        )
        return client.query(
            self.workspace,
            question,
            project=project,
            session_id=session_id,
            task="mission drift/failure recovery planning",
        )


__all__ = [
    "DriftAssessment",
    "DriftDecision",
    "FailureGuidanceRequest",
    "MissionAction",
    "MissionCheckpoint",
    "MissionContract",
    "MissionDriftGuard",
    "MissionGuardError",
    "MissionStore",
]
