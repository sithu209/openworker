"""E7.4 canonical handoff submission adapter.

This module submits a persona product plan to the *existing* AI-Engineering-OS control
plane.  It does not execute a second agent loop, invent a second Job/Artifact model, or
perform external send/publish actions.

Submission is intentionally conservative:

* a Project id is explicit; OpenWorker never guesses a project from disk or account state;
* Job reuse is explicit and validated; otherwise a new canonical Job is created;
* handoff capability metadata is attached to the canonical Job, not copied into a new registry;
* downstream artifacts are read back from AI-Engineering-OS and converted with the existing
  ``os_artifact_ref`` helper;
* delivery readiness requires both persona QA and canonical AI-Engineering-OS approval;
* this adapter never calls ``publish_job`` or a connector sender.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from coworker.engineering.digital_thread import EvidenceRef, os_artifact_ref
from coworker.engineering.engineering_os import EngineeringOSClient

from .product_contract import (
    DeliveryEvidence,
    PersonaProductPlan,
    ProductContractError,
    QAStatus,
    delivery_evidence,
)
from .task_package import PersonaTaskPackage


class SubmissionContractError(ProductContractError):
    """Raised when E7.4 cannot preserve canonical Job/authority identity."""


@dataclass(frozen=True)
class PersonaJobSubmission:
    """Reference to the canonical AI-Engineering-OS Job created/reused for a persona plan."""

    project_id: str
    job_id: str
    reused: bool
    task_package_path: str
    persona: str
    session_id: str
    handoff_capabilities: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-job-submission/v1",
            "authority": "AI-Engineering-OS",
            "project_id": self.project_id,
            "job_id": self.job_id,
            "reused": self.reused,
            "task_package_path": self.task_package_path,
            "persona": self.persona,
            "session_id": self.session_id,
            "handoff_capabilities": list(self.handoff_capabilities),
            "external_action_performed": False,
        }


@dataclass(frozen=True)
class PersonaDeliveryAssessment:
    """QA + canonical approval snapshot.  This object never performs delivery/publish."""

    job_id: str
    approved: bool
    approval: Mapping[str, Any]
    evidence: DeliveryEvidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-delivery-assessment/v1",
            "authority": "AI-Engineering-OS",
            "job_id": self.job_id,
            "approved": self.approved,
            "approval": dict(self.approval),
            "evidence": self.evidence.to_dict(),
            "publish_performed": False,
            "external_send_performed": False,
        }


def _required_text(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise SubmissionContractError(f"{field} must not be empty")
    return text


def _expected_deliverables(plan: PersonaProductPlan) -> list[str]:
    values: list[str] = []
    for handoff in plan.handoffs:
        for artifact in handoff.expected_artifacts:
            text = str(artifact).strip()
            if text and text not in values:
                values.append(text)
    return values


def _handoff_capabilities(plan: PersonaProductPlan) -> tuple[str, ...]:
    values = sorted({handoff.capability.value for handoff in plan.handoffs})
    return tuple(values)


def _canonical_job_metadata(plan: PersonaProductPlan) -> dict[str, Any]:
    return {
        "source": "openworker-e7-persona",
        "persona": plan.session.persona.value,
        "persona_session_id": plan.session.session_id,
        "workspace_id": plan.session.workspace_id,
        "task_package_path": plan.task_package_path,
        "product_plan_schema": "openworker.persona-product-plan/v1",
        "handoff_capabilities": list(_handoff_capabilities(plan)),
        "runtime_policy": "NativeRuntime default; Harness explicit opt-in",
    }


def _validate_reused_job(
    job: Mapping[str, Any],
    *,
    project_id: str,
    plan: PersonaProductPlan,
) -> str:
    job_id = _required_text(job.get("id"), "reused job id")
    actual_project = _required_text(job.get("project_id"), "reused job project_id")
    if actual_project != project_id:
        raise SubmissionContractError("reused canonical Job belongs to a different project")

    metadata = job.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise SubmissionContractError("reused canonical Job metadata must be an object")
    metadata = metadata or {}
    expected = _canonical_job_metadata(plan)
    for key in ("persona", "persona_session_id", "workspace_id", "task_package_path"):
        current = metadata.get(key)
        if current is not None and str(current) != str(expected[key]):
            raise SubmissionContractError(f"reused canonical Job metadata mismatch: {key}")
    return job_id


def submit_product_plan(
    client: EngineeringOSClient,
    plan: PersonaProductPlan,
    package: PersonaTaskPackage,
    *,
    project_id: str,
    job_code: str,
    existing_job_id: str | None = None,
    priority: str | None = None,
) -> PersonaJobSubmission:
    """Create or explicitly reuse the canonical AI-Engineering-OS Job for one persona plan.

    Creating the Job is the handoff submission.  This function deliberately does not transition
    the Job, execute specialist flows, approve artifacts, publish a delivery, or invoke connectors.
    Those operations remain owned by existing canonical tools and permission gates.
    """

    project_id = _required_text(project_id, "project_id")
    job_code = _required_text(job_code, "job_code")
    if package.kind is not plan.session.persona:
        raise SubmissionContractError("product plan persona must match task package kind")
    if not plan.handoffs:
        raise SubmissionContractError("persona product plan has no canonical handoff to submit")

    if existing_job_id is not None:
        requested = _required_text(existing_job_id, "existing_job_id")
        job = client.get_job(requested)
        job_id = _validate_reused_job(job, project_id=project_id, plan=plan)
        reused = True
    else:
        job = client.create_job(
            project_id=project_id,
            code=job_code,
            name=package.title,
            user_request=package.brief,
            expected_deliverables=_expected_deliverables(plan),
            priority=priority,
            metadata=_canonical_job_metadata(plan),
        )
        job_id = _required_text(job.get("id"), "created job id")
        actual_project = _required_text(job.get("project_id"), "created job project_id")
        if actual_project != project_id:
            raise SubmissionContractError("created canonical Job returned a different project_id")
        reused = False

    return PersonaJobSubmission(
        project_id=project_id,
        job_id=job_id,
        reused=reused,
        task_package_path=plan.task_package_path,
        persona=plan.session.persona.value,
        session_id=plan.session.session_id,
        handoff_capabilities=_handoff_capabilities(plan),
    )


def collect_job_artifacts(
    client: EngineeringOSClient,
    job_id: str,
) -> tuple[EvidenceRef, ...]:
    """Read real canonical artifacts and map them into the existing Digital Thread identity."""

    job_id = _required_text(job_id, "job_id")
    try:
        return tuple(os_artifact_ref(item) for item in client.list_job_artifacts(job_id))
    except (ValueError, TypeError) as exc:
        raise SubmissionContractError(f"invalid canonical artifact evidence: {exc}") from exc


def assess_delivery_readiness(
    client: EngineeringOSClient,
    job_id: str,
    *,
    qa_passed: bool,
    qa_notes: Iterable[str] = (),
) -> PersonaDeliveryAssessment:
    """Combine persona QA with canonical approval without performing publish/send.

    ``delivery_ready`` is true only when QA passed, at least one real artifact exists, and
    AI-Engineering-OS reports the current Job approved.  A passed QA with zero artifacts fails
    closed rather than manufacturing evidence.
    """

    job_id = _required_text(job_id, "job_id")
    artifacts = collect_job_artifacts(client, job_id)
    approval = client.approval_status(job_id)
    approved = approval.get("approved") is True
    status = QAStatus.PASSED if qa_passed else QAStatus.FAILED
    try:
        evidence = delivery_evidence(
            artifacts,
            qa_status=status,
            qa_notes=qa_notes,
            delivery_ready=bool(qa_passed and artifacts and approved),
        )
    except ProductContractError as exc:
        raise SubmissionContractError(str(exc)) from exc
    return PersonaDeliveryAssessment(
        job_id=job_id,
        approved=approved,
        approval=approval,
        evidence=evidence,
    )
