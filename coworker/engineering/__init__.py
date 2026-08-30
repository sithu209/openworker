"""Engineering extension layer for OpenWorker.

This package is intentionally thin: OpenWorker owns orchestration, permissions, sessions,
and connectors; domain repositories own engineering logic. Integrations should be added
through adapters instead of embedding domain implementations into the core runtime.
"""

from .adapters import EngineeringAdapter, EngineeringAdapterRegistry, EngineeringCapability
from .comfyx_long_job import (
    ComfyXArtifactError, ComfyXCLIClient, ComfyXCLIError, ComfyXLongJobError,
    ComfyXLongJobReport, VerifiedMP4, inspect_mp4, verify_comfyx_long_job,
    verify_video_artifact, verify_with_engineering_os,
)
from .contracts import AdapterDescriptor, ApprovalPolicy, HealthReport, HealthStatus
from .digital_thread import (
    DigitalThread, EvidenceKind, EvidenceRef, ProvenanceLink, RelationKind, add_all,
    bim_forge_artifact_ref, design_forge_artifact_ref, engsketch_version_refs,
    os_artifact_ref, os_job_ref,
)
from .engineering_os import (
    EngineeringOSClient, EngineeringOSConfig, EngineeringOSContractError, EngineeringOSError,
    EngineeringOSHTTPError, EngineeringOSTimeoutError, EngineeringOSTransport,
    EngineeringOSTransportError, TransportResponse, UrllibEngineeringOSTransport,
)
from .flow_client import EngineeringOSFlowClient
from .golden_job import GoldenJobResult, GoldenJobReviewResult, RCColumnGoldenJob
from .runtime_ab import (
    ArtifactFingerprint, RuntimeABError, RuntimeABReport, RuntimeCaseResult,
    compare_runtime_cases, fingerprint_artifacts, run_rc_runtime_ab, run_runtime_case,
)
from .specialists import (
    BIMForgeAdapter, CommandResult, DesignForgeAdapter, EngSketchAdapter, KnowGraphAdapter,
    SubprocessCommandRunner, core_specialist_adapters,
)
from .tools import engineering_os_tools

__all__ = [
    "AdapterDescriptor", "ApprovalPolicy", "ArtifactFingerprint", "BIMForgeAdapter",
    "CommandResult", "ComfyXArtifactError", "ComfyXCLIClient", "ComfyXCLIError",
    "ComfyXLongJobError", "ComfyXLongJobReport", "DesignForgeAdapter", "DigitalThread",
    "EngineeringAdapter", "EngineeringAdapterRegistry", "EngineeringCapability",
    "EngineeringOSClient", "EngineeringOSConfig", "EngineeringOSContractError",
    "EngineeringOSError", "EngineeringOSFlowClient", "EngineeringOSHTTPError",
    "EngineeringOSTimeoutError", "EngineeringOSTransport", "EngineeringOSTransportError",
    "EngSketchAdapter", "EvidenceKind", "EvidenceRef", "GoldenJobResult",
    "GoldenJobReviewResult", "HealthReport", "HealthStatus", "KnowGraphAdapter",
    "ProvenanceLink", "RCColumnGoldenJob", "RelationKind", "RuntimeABError",
    "RuntimeABReport", "RuntimeCaseResult", "SubprocessCommandRunner", "TransportResponse",
    "UrllibEngineeringOSTransport", "VerifiedMP4", "add_all", "bim_forge_artifact_ref",
    "compare_runtime_cases", "core_specialist_adapters", "design_forge_artifact_ref",
    "engineering_os_tools", "engsketch_version_refs", "fingerprint_artifacts", "inspect_mp4",
    "os_artifact_ref", "os_job_ref", "run_rc_runtime_ab", "run_runtime_case",
    "verify_comfyx_long_job", "verify_video_artifact", "verify_with_engineering_os",
]
