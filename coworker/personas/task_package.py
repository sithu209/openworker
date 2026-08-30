"""E7 persona-level task packages.

These objects describe work; they do not execute tools, publish artifacts, send messages,
or create automations.  Execution stays with the existing OpenWorker runtime and canonical
authorities.  Keeping the package declarative gives Media/Company personas a stable handoff
shape without creating a second workflow engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


class TaskPackageError(ValueError):
    """Raised when an E7 task package would weaken an authority/safety boundary."""


class PackageKind(str, Enum):
    MEDIA = "media"
    COMPANY = "company"


class ActionClass(str, Enum):
    LOCAL = "local"
    CANONICAL = "canonical"
    EXTERNAL = "external"


@dataclass(frozen=True)
class WorkStep:
    id: str
    title: str
    action: ActionClass = ActionClass.LOCAL
    authority: str = "openworker"
    expected_artifacts: tuple[str, ...] = ()
    requires_approval: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip():
            raise TaskPackageError("work step id/title must be non-empty")
        if self.action is ActionClass.CANONICAL and self.authority == "openworker":
            raise TaskPackageError("canonical execution must name its downstream authority")
        if self.action is ActionClass.EXTERNAL and not self.requires_approval:
            raise TaskPackageError("external send/publish/commitment steps require approval")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "action": self.action.value,
            "authority": self.authority,
            "expected_artifacts": list(self.expected_artifacts),
            "requires_approval": self.requires_approval,
        }


@dataclass(frozen=True)
class PersonaTaskPackage:
    kind: PackageKind
    title: str
    brief: str
    inputs: tuple[str, ...] = ()
    steps: tuple[WorkStep, ...] = ()
    evidence: tuple[str, ...] = ()
    follow_up: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.brief.strip():
            raise TaskPackageError("task package title/brief must be non-empty")
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise TaskPackageError("work step ids must be unique")

    @property
    def has_external_actions(self) -> bool:
        return any(step.action is ActionClass.EXTERNAL for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-task-package/v1",
            "kind": self.kind.value,
            "title": self.title,
            "brief": self.brief,
            "inputs": list(self.inputs),
            "steps": [step.to_dict() for step in self.steps],
            "evidence": list(self.evidence),
            "follow_up": list(self.follow_up),
            "metadata": dict(self.metadata),
        }


def _tuple(values: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in (values or ()) if str(value).strip())


def media_task_package(
    *,
    title: str,
    brief: str,
    inputs: Iterable[str] = (),
    deliverables: Iterable[str] = (),
    publish_target: str | None = None,
) -> PersonaTaskPackage:
    """Build a media production handoff without performing generation or publication."""
    outputs = _tuple(deliverables) or ("media-delivery-package",)
    steps = [
        WorkStep("brief", "Ground the media brief and source inputs"),
        WorkStep("plan", "Prepare script, prompt, shot, and production plan"),
        WorkStep(
            "produce",
            "Request canonical media generation through the existing execution authority",
            action=ActionClass.CANONICAL,
            authority="AI-Engineering-OS / specialist media engine",
            expected_artifacts=outputs,
        ),
        WorkStep("qa", "Inspect generated artifacts and prepare QA/evidence package", expected_artifacts=("qa-report",)),
    ]
    if publish_target:
        steps.append(
            WorkStep(
                "publish",
                f"Publish approved media package to {publish_target}",
                action=ActionClass.EXTERNAL,
                authority="existing connector / publishing surface",
                expected_artifacts=("publish-receipt",),
                requires_approval=True,
            )
        )
    return PersonaTaskPackage(
        kind=PackageKind.MEDIA,
        title=title,
        brief=brief,
        inputs=_tuple(inputs),
        steps=tuple(steps),
        evidence=("ArtifactRef/checksum lineage", "generation/QA evidence"),
        follow_up=("Record audience/quality feedback only when supported by evidence",),
    )


def company_task_package(
    *,
    title: str,
    brief: str,
    inputs: Iterable[str] = (),
    needs_engineering: bool = False,
    needs_media: bool = False,
    external_target: str | None = None,
) -> PersonaTaskPackage:
    """Build a company work package while keeping drafts separate from external actions."""
    steps = [
        WorkStep("ground", "Ground the request, evidence, constraints, and unknowns"),
        WorkStep("work", "Prepare research, proposal, project, or delivery work package", expected_artifacts=("work-package",)),
    ]
    if needs_engineering:
        steps.append(
            WorkStep(
                "engineering-handoff",
                "Hand engineering work to canonical engineering tools",
                action=ActionClass.CANONICAL,
                authority="AI-Engineering-OS",
                expected_artifacts=("engineering-artifacts",),
            )
        )
    if needs_media:
        steps.append(
            WorkStep(
                "media-handoff",
                "Hand media production to the existing media execution authority",
                action=ActionClass.CANONICAL,
                authority="AI-Engineering-OS / specialist media engine",
                expected_artifacts=("media-delivery-package",),
            )
        )
    steps.append(WorkStep("delivery", "Prepare evidence-backed delivery and follow-up plan", expected_artifacts=("delivery-package",)))
    if external_target:
        steps.append(
            WorkStep(
                "external-send",
                f"Send the approved package to {external_target}",
                action=ActionClass.EXTERNAL,
                authority="existing connector / messaging surface",
                expected_artifacts=("send-receipt",),
                requires_approval=True,
            )
        )
    return PersonaTaskPackage(
        kind=PackageKind.COMPANY,
        title=title,
        brief=brief,
        inputs=_tuple(inputs),
        steps=tuple(steps),
        evidence=("source evidence", "decision/artifact lineage"),
        follow_up=("Use existing scheduler for recurring follow-up when explicitly requested",),
    )
