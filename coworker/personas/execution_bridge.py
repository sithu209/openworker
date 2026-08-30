"""E7.5/E7.6 bridge from persona submissions to existing canonical execution surfaces.

This module does not create another executor or tool registry. It validates persona Job
identity, prepares calls for existing OpenWorker engineering/media tools, and reads canonical
AI-Engineering-OS Job/Artifact/Review state back into one immutable result snapshot.

Media generation routes through the vetted ``engineering_generate_minimax_h3`` facade, which
adapts ComfyX's authoritative ``comfyx.minimax_h3.generate`` ai-tool-protocol surface. E7 does
not reproduce ComfyX workflow construction, runtime discovery, submission, polling, or artifact
extraction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from coworker.engineering.digital_thread import EvidenceRef, os_artifact_ref, os_job_ref

from .submission import PersonaJobSubmission, SubmissionContractError


class ExecutionBridgeError(SubmissionContractError):
    """Raised when E7 cannot preserve canonical execution identity or authority."""


class UnsupportedCanonicalFlowError(ExecutionBridgeError):
    """Raised when a persona asks for a flow not exposed by the existing canonical facade."""


@dataclass(frozen=True)
class CanonicalToolCall:
    """Descriptor for one existing Tool Registry invocation; this object never executes it."""

    tool_name: str
    arguments: Mapping[str, Any]
    requires_approval: bool
    authority: str = "AI-Engineering-OS"

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ExecutionBridgeError("tool_name must not be empty")
        if self.authority != "AI-Engineering-OS":
            raise ExecutionBridgeError("canonical execution authority must be AI-Engineering-OS")
        object.__setattr__(self, "arguments", dict(self.arguments))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-canonical-tool-call/v1",
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "requires_approval": self.requires_approval,
            "authority": self.authority,
            "execution": "not-performed",
        }


@dataclass(frozen=True)
class CanonicalResultSnapshot:
    """Read-only snapshot of state owned by AI-Engineering-OS after canonical execution."""

    submission: PersonaJobSubmission
    job: EvidenceRef
    status: str
    artifacts: tuple[EvidenceRef, ...]
    reviews: tuple[Mapping[str, Any], ...]
    approved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-canonical-result/v1",
            "authority": "AI-Engineering-OS",
            "submission": self.submission.to_dict(),
            "job": self.job.to_dict(),
            "status": self.status,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "reviews": [dict(item) for item in self.reviews],
            "approved": self.approved,
            "publish_performed": False,
            "external_send_performed": False,
        }


class CanonicalResultReader(Protocol):
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def list_job_artifacts(self, job_id: str) -> Sequence[dict[str, Any]]: ...
    def list_job_reviews(self, job_id: str) -> Sequence[dict[str, Any]]: ...
    def approval_status(self, job_id: str) -> dict[str, Any]: ...


def _required_text(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ExecutionBridgeError(f"{field} must not be empty")
    return text


def _validate_submission_job(submission: PersonaJobSubmission, job: Mapping[str, Any]) -> str:
    job_id = _required_text(job.get("id"), "job.id")
    project_id = _required_text(job.get("project_id"), "job.project_id")
    if job_id != submission.job_id:
        raise ExecutionBridgeError("canonical Job id does not match persona submission")
    if project_id != submission.project_id:
        raise ExecutionBridgeError("canonical Job project_id does not match persona submission")
    metadata = job.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ExecutionBridgeError("canonical Job metadata must be an object")
    metadata = metadata or {}
    for key, expected in {
        "persona": submission.persona,
        "persona_session_id": submission.session_id,
        "task_package_path": submission.task_package_path,
    }.items():
        actual = metadata.get(key)
        if actual is not None and str(actual) != str(expected):
            raise ExecutionBridgeError(f"canonical Job lineage mismatch: {key}")
    return _required_text(job.get("status"), "job.status")


def rc_column_tool_call(
    submission: PersonaJobSubmission,
    column: Mapping[str, Any],
) -> CanonicalToolCall:
    """Build the existing approved engineering flow invocation for one submitted Job."""

    if "engineering" not in submission.handoff_capabilities:
        raise UnsupportedCanonicalFlowError("submission does not declare engineering capability")
    if not isinstance(column, Mapping):
        raise ExecutionBridgeError("column must be a mapping")
    return CanonicalToolCall(
        tool_name="engineering_execute_rc_column_flow",
        arguments={"job_id": submission.job_id, "column": dict(column)},
        requires_approval=True,
    )


def media_submit_tool_call(
    submission: PersonaJobSubmission,
    payload: Mapping[str, Any],
) -> CanonicalToolCall:
    """Describe the vetted ComfyX MiniMax H3 facade call; execution stays in Tool Registry."""

    if "media" not in submission.handoff_capabilities:
        raise UnsupportedCanonicalFlowError("submission does not declare media capability")
    if not isinstance(payload, Mapping):
        raise ExecutionBridgeError("media payload must be a mapping")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ExecutionBridgeError("media payload prompt must not be empty")
    if payload.get("compile_only") is True:
        raise ExecutionBridgeError("media submit cannot use compile_only=true")
    return CanonicalToolCall(
        tool_name="engineering_generate_minimax_h3",
        arguments=dict(payload),
        requires_approval=True,
    )


def read_canonical_result(
    reader: CanonicalResultReader,
    submission: PersonaJobSubmission,
) -> CanonicalResultSnapshot:
    """Read Job/Artifact/Review/approval state after execution without publishing anything."""

    job = reader.get_job(submission.job_id)
    status = _validate_submission_job(submission, job)
    try:
        job_ref = os_job_ref(job)
        artifacts = tuple(os_artifact_ref(item) for item in reader.list_job_artifacts(submission.job_id))
    except (ValueError, TypeError) as exc:
        raise ExecutionBridgeError(f"invalid canonical result evidence: {exc}") from exc

    reviews_raw = reader.list_job_reviews(submission.job_id)
    reviews: list[Mapping[str, Any]] = []
    for item in reviews_raw:
        if not isinstance(item, Mapping):
            raise ExecutionBridgeError("canonical review record must be an object")
        if item.get("job_id") not in (None, submission.job_id):
            raise ExecutionBridgeError("canonical review belongs to a different Job")
        reviews.append(dict(item))

    approval = reader.approval_status(submission.job_id)
    if not isinstance(approval, Mapping) or not isinstance(approval.get("approved"), bool):
        raise ExecutionBridgeError("canonical approval status must contain approved boolean")

    return CanonicalResultSnapshot(
        submission=submission,
        job=job_ref,
        status=status,
        artifacts=artifacts,
        reviews=tuple(reviews),
        approved=approval["approved"],
    )
