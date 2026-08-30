"""E7.3 persona-facing product contract.

This module connects Media/Company persona sessions to the existing Project Workspace and
canonical AI-Engineering-OS handoff/evidence model.  It is deliberately *not* an executor:
it does not run agents, tools, schedulers, connectors, media engines, or publish actions.

The contract keeps five product boundaries explicit:

* persona session -> declarative PersonaTaskPackage
* task package -> durable Project Workspace record
* canonical steps -> AI-Engineering-OS handoff descriptors
* external steps -> approval metadata only (never implicit send/publish)
* downstream artifacts -> existing EvidenceRef + QA/delivery envelope

NativeRuntime/Harness selection remains owned by the existing runtime manager.  Scheduler,
connector and Artifact Registry implementations are referenced, never duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from coworker.engineering.digital_thread import EvidenceKind, EvidenceRef

from .task_package import ActionClass, PackageKind, PersonaTaskPackage, WorkStep


class ProductContractError(ValueError):
    """Raised when a persona product contract would weaken a product boundary."""


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _segment(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not _SAFE_SEGMENT.fullmatch(text) or text in {".", ".."}:
        raise ProductContractError(
            f"{field_name} must be a safe workspace identifier (letters, numbers, ._- only)"
        )
    return text


@dataclass(frozen=True)
class PersonaSession:
    """Identity needed to bind a task package to one existing OpenWorker session/workspace."""

    persona: PackageKind | str
    session_id: str
    workspace_id: str

    def __post_init__(self) -> None:
        persona = self.persona
        if not isinstance(persona, PackageKind):
            try:
                persona = PackageKind(str(persona).strip().lower())
            except ValueError as exc:
                raise ProductContractError("persona must be media or company") from exc
        object.__setattr__(self, "persona", persona)
        object.__setattr__(self, "session_id", _segment(self.session_id, "session_id"))
        object.__setattr__(self, "workspace_id", _segment(self.workspace_id, "workspace_id"))

    def to_dict(self) -> dict[str, str]:
        return {
            "persona": self.persona.value,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
        }


class HandoffCapability(str, Enum):
    ENGINEERING = "engineering"
    MEDIA = "media"


@dataclass(frozen=True)
class CanonicalHandoff:
    """Descriptor for work that must be submitted through the existing canonical authority."""

    step_id: str
    capability: HandoffCapability
    authority: str
    source_authority: str
    expected_artifacts: tuple[str, ...] = ()
    task_package_path: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _segment(self.step_id, "step_id"))
        if self.authority != "AI-Engineering-OS":
            raise ProductContractError("canonical persona handoff authority must be AI-Engineering-OS")
        if not self.source_authority.strip():
            raise ProductContractError("source_authority must not be empty")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": "openworker.persona-canonical-handoff/v1",
            "step_id": self.step_id,
            "capability": self.capability.value,
            "authority": self.authority,
            "source_authority": self.source_authority,
            "expected_artifacts": list(self.expected_artifacts),
            "metadata": dict(self.metadata),
        }
        if self.task_package_path:
            payload["task_package_path"] = self.task_package_path
        return payload


@dataclass(frozen=True)
class ExternalApprovalIntent:
    """Approval-only representation of an external send/publish/commitment step."""

    step_id: str
    title: str
    authority: str
    requires_approval: bool

    def __post_init__(self) -> None:
        if not self.requires_approval:
            raise ProductContractError("external intent must preserve requires_approval=True")
        if not self.title.strip() or not self.authority.strip():
            raise ProductContractError("external intent title/authority must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "authority": self.authority,
            "requires_approval": True,
            "execution": "not-performed",
        }


@dataclass(frozen=True)
class PersonaProductPlan:
    """Persisted package plus safe descriptors for existing downstream systems."""

    session: PersonaSession
    task_package_path: str
    handoffs: tuple[CanonicalHandoff, ...]
    external_approval_intents: tuple[ExternalApprovalIntent, ...]
    scheduler_binding: str = "coworker.automation (existing scheduler)"
    connector_binding: str = "coworker.connectors (existing connector layer)"
    artifact_binding: str = "AI-Engineering-OS Artifact Registry / Workspace Artifact Publisher"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-product-plan/v1",
            "session": self.session.to_dict(),
            "task_package_path": self.task_package_path,
            "handoffs": [item.to_dict() for item in self.handoffs],
            "external_approval_intents": [
                item.to_dict() for item in self.external_approval_intents
            ],
            "bindings": {
                "scheduler": self.scheduler_binding,
                "connectors": self.connector_binding,
                "artifacts": self.artifact_binding,
            },
        }


class QAStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryEvidence:
    """Evidence-backed QA/delivery envelope; does not publish or send anything."""

    artifacts: tuple[EvidenceRef, ...]
    qa_status: QAStatus = QAStatus.PENDING
    qa_notes: tuple[str, ...] = ()
    delivery_ready: bool = False

    def __post_init__(self) -> None:
        if self.delivery_ready and self.qa_status is not QAStatus.PASSED:
            raise ProductContractError("delivery_ready requires QAStatus.PASSED")
        if self.qa_status is QAStatus.PASSED and not self.artifacts:
            raise ProductContractError("passed QA requires at least one real artifact reference")
        for artifact in self.artifacts:
            if artifact.kind is EvidenceKind.ARTIFACT and not artifact.checksum:
                raise ProductContractError("artifact delivery evidence requires checksum lineage")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-delivery-evidence/v1",
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "qa": {"status": self.qa_status.value, "notes": list(self.qa_notes)},
            "delivery_ready": self.delivery_ready,
            "external_delivery_performed": False,
        }


def _relative_workspace_path(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix()


def save_task_package(
    workspace: str | Path,
    session: PersonaSession,
    package: PersonaTaskPackage,
    *,
    package_id: str,
) -> str:
    """Persist a package below ``.openworker/persona-tasks`` and return its relative path.

    The function only writes the declarative JSON record.  It does not enqueue or execute work.
    ``Path.resolve`` plus safe path segments prevents session/package identifiers from escaping the
    selected Project Workspace.
    """

    if package.kind is not session.persona:
        raise ProductContractError("persona session kind must match task package kind")
    package_id = _segment(package_id, "package_id")
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = (
        root
        / ".openworker"
        / "persona-tasks"
        / session.persona.value
        / session.session_id
        / f"{package_id}.json"
    ).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ProductContractError("task package path escaped Project Workspace") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "openworker.persona-workspace-task/v1",
        "session": session.to_dict(),
        "task_package": package.to_dict(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(destination)
    return _relative_workspace_path(destination, root)


def _handoff_capability(step: WorkStep, package: PersonaTaskPackage) -> HandoffCapability:
    if step.id == "media-handoff" or (package.kind is PackageKind.MEDIA and step.id == "produce"):
        return HandoffCapability.MEDIA
    return HandoffCapability.ENGINEERING


def canonical_handoffs(
    package: PersonaTaskPackage,
    *,
    task_package_path: str | None = None,
) -> tuple[CanonicalHandoff, ...]:
    """Map canonical package steps to the existing AI-Engineering-OS control plane."""

    handoffs: list[CanonicalHandoff] = []
    for step in package.steps:
        if step.action is not ActionClass.CANONICAL:
            continue
        handoffs.append(
            CanonicalHandoff(
                step_id=step.id,
                capability=_handoff_capability(step, package),
                authority="AI-Engineering-OS",
                source_authority=step.authority,
                expected_artifacts=step.expected_artifacts,
                task_package_path=task_package_path,
                metadata={
                    "runtime_policy": "NativeRuntime default; Harness explicit opt-in",
                    "execution": "descriptor-only",
                },
            )
        )
    return tuple(handoffs)


def external_approval_intents(package: PersonaTaskPackage) -> tuple[ExternalApprovalIntent, ...]:
    """Extract approval metadata without invoking the existing connector/publishing layer."""

    intents: list[ExternalApprovalIntent] = []
    for step in package.steps:
        if step.action is ActionClass.EXTERNAL:
            intents.append(
                ExternalApprovalIntent(
                    step_id=step.id,
                    title=step.title,
                    authority=step.authority,
                    requires_approval=step.requires_approval,
                )
            )
    return tuple(intents)


def build_product_plan(
    workspace: str | Path,
    session: PersonaSession,
    package: PersonaTaskPackage,
    *,
    package_id: str,
) -> PersonaProductPlan:
    """Create the E7.3 product contract without creating a second execution loop."""

    path = save_task_package(workspace, session, package, package_id=package_id)
    return PersonaProductPlan(
        session=session,
        task_package_path=path,
        handoffs=canonical_handoffs(package, task_package_path=path),
        external_approval_intents=external_approval_intents(package),
    )


def delivery_evidence(
    artifacts: Iterable[EvidenceRef],
    *,
    qa_status: QAStatus = QAStatus.PENDING,
    qa_notes: Iterable[str] = (),
    delivery_ready: bool = False,
) -> DeliveryEvidence:
    """Build a delivery envelope around existing ArtifactRef/EvidenceRef identities."""

    return DeliveryEvidence(
        artifacts=tuple(artifacts),
        qa_status=qa_status,
        qa_notes=tuple(str(note).strip() for note in qa_notes if str(note).strip()),
        delivery_ready=delivery_ready,
    )
