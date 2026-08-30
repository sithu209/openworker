"""AI-Engineering-OS managed RC-column flow.

E6.3+ deliberately delegates calculation, drawing and BIM orchestration to the existing
AI-Engineering-OS rcflow instead of reproducing that workflow inside OpenWorker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .digital_thread import DigitalThread, RelationKind, os_artifact_ref, os_job_ref
from .engineering_os import EngineeringOSContractError


_REQUIRED = (
    "component_id", "width_mm", "depth_mm", "clear_height_mm", "concrete_grade",
    "steel_grade", "axial_force_kn", "moment_x_knm",
)


class RCFlowControlPlane(Protocol):
    def execute_rc_column_flow(self, *, job_id: str, column: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ManagedRCFlowResult:
    job: dict[str, Any]
    tasks: tuple[dict[str, Any], ...]
    stages: tuple[dict[str, Any], ...]
    artifacts: tuple[dict[str, Any], ...]
    digital_thread: dict[str, Any]


def execute_managed_rc_column(
    client: RCFlowControlPlane,
    *,
    job_id: str,
    column: Mapping[str, Any],
) -> ManagedRCFlowResult:
    """Execute the authoritative OS RC flow: design -> drawing -> BIM -> review."""
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id must not be empty")
    job_id = job_id.strip()
    payload = dict(column)
    missing = [name for name in _REQUIRED if payload.get(name) in (None, "")]
    if missing:
        raise ValueError(f"managed RC column flow missing fields: {', '.join(missing)}")

    result = client.execute_rc_column_flow(job_id=job_id, column=payload)
    job = result.get("job")
    tasks = result.get("tasks")
    stages = result.get("stages")
    artifacts = result.get("artifacts")
    if not isinstance(job, dict):
        raise EngineeringOSContractError("rc-column flow response must contain job object")
    if job.get("id") != job_id:
        raise EngineeringOSContractError("rc-column flow returned inconsistent job identity")
    if job.get("status") != "review":
        raise EngineeringOSContractError("rc-column flow must close in review state")
    for name, value in (("tasks", tasks), ("stages", stages), ("artifacts", artifacts)):
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise EngineeringOSContractError(f"rc-column flow response must contain {name} object list")
    kinds = {str(item.get("kind", "")).lower() for item in artifacts}
    if not any("draw" in kind or "svg" in kind or "png" in kind for kind in kinds):
        raise EngineeringOSContractError("rc-column flow returned no drawing artifact")
    if not any("bim" in kind or "ifc" in kind for kind in kinds):
        raise EngineeringOSContractError("rc-column flow returned no BIM/IFC artifact")

    thread = DigitalThread()
    job_ref = thread.add(os_job_ref(job))
    for item in artifacts:
        artifact_ref = thread.add(os_artifact_ref(item))
        thread.link(artifact_ref, RelationKind.BELONGS_TO_JOB, job_ref)

    return ManagedRCFlowResult(
        job=job,
        tasks=tuple(tasks),
        stages=tuple(stages),
        artifacts=tuple(artifacts),
        digital_thread=thread.to_dict(),
    )
