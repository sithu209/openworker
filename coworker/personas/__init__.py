"""Personas — specialized coworkers as declarative, skill-shaped bundles.

A persona is a manifest (YAML frontmatter + a markdown body that is the system prompt) that
composes vetted catalog capabilities, a family/workspace shape, and lifecycle metadata. The
built-in surfaces (Code, Cowork, Chat, Ops) are themselves manifests — the same format third
parties use. See `platform/docs/PERSONAS.md`.
"""

from __future__ import annotations

from .manifest import PersonaManifest, ManifestError, parse_manifest, load_manifest_file
from .registry import PersonaRegistry, PersonaState, DEFAULT_PERSONA_ID
from .task_package import (
    ActionClass,
    PackageKind,
    PersonaTaskPackage,
    TaskPackageError,
    WorkStep,
    company_task_package,
    media_task_package,
)
from .product_contract import (
    CanonicalHandoff,
    DeliveryEvidence,
    ExternalApprovalIntent,
    HandoffCapability,
    PersonaProductPlan,
    PersonaSession,
    ProductContractError,
    QAStatus,
    build_product_plan,
    canonical_handoffs,
    delivery_evidence,
    external_approval_intents,
    save_task_package,
)
from .submission import (
    PersonaDeliveryAssessment,
    PersonaJobSubmission,
    SubmissionContractError,
    assess_delivery_readiness,
    collect_job_artifacts,
    submit_product_plan,
)
from .execution_bridge import (
    CanonicalResultSnapshot,
    CanonicalToolCall,
    ExecutionBridgeError,
    UnsupportedCanonicalFlowError,
    media_submit_tool_call,
    rc_column_tool_call,
    read_canonical_result,
)
from .media_evidence import (
    MediaArtifactWriter,
    MediaEvidenceSyncError,
    MediaEvidenceSyncResult,
    sync_comfyx_media_evidence,
)

__all__ = [
    "PersonaManifest",
    "ManifestError",
    "parse_manifest",
    "load_manifest_file",
    "PersonaRegistry",
    "PersonaState",
    "DEFAULT_PERSONA_ID",
    "ActionClass",
    "PackageKind",
    "PersonaTaskPackage",
    "TaskPackageError",
    "WorkStep",
    "company_task_package",
    "media_task_package",
    "CanonicalHandoff",
    "DeliveryEvidence",
    "ExternalApprovalIntent",
    "HandoffCapability",
    "PersonaProductPlan",
    "PersonaSession",
    "ProductContractError",
    "QAStatus",
    "build_product_plan",
    "canonical_handoffs",
    "delivery_evidence",
    "external_approval_intents",
    "save_task_package",
    "PersonaDeliveryAssessment",
    "PersonaJobSubmission",
    "SubmissionContractError",
    "assess_delivery_readiness",
    "collect_job_artifacts",
    "submit_product_plan",
    "CanonicalResultSnapshot",
    "CanonicalToolCall",
    "ExecutionBridgeError",
    "UnsupportedCanonicalFlowError",
    "media_submit_tool_call",
    "rc_column_tool_call",
    "read_canonical_result",
    "MediaArtifactWriter",
    "MediaEvidenceSyncError",
    "MediaEvidenceSyncResult",
    "sync_comfyx_media_evidence",
]
