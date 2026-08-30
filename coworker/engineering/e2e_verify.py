"""Deployable E2E verification harness for the OS-managed RC-column Golden Path.

This module performs real side effects when run against AI-Engineering-OS. It intentionally
requires an explicit confirmation flag at the CLI boundary and never auto-approves or
publishes unless reviewer/publisher identities are supplied.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping

from .flow_client import EngineeringOSFlowClient
from .engineering_os import EngineeringOSConfig
from .managed_rcflow import ManagedRCFlowResult, execute_managed_rc_column


@dataclass(frozen=True)
class E2EVerificationResult:
    project_id: str
    job: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    approval_status: dict[str, Any] | None
    delivery: dict[str, Any] | None
    digital_thread: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "job": self.job,
            "artifacts": list(self.artifacts),
            "approval_status": self.approval_status,
            "delivery": self.delivery,
            "digital_thread": self.digital_thread,
        }


def run_rc_column_e2e(
    client: EngineeringOSFlowClient,
    *,
    project_id: str,
    job_code: str,
    column: Mapping[str, Any],
    reviewer: str | None = None,
    publisher: str | None = None,
) -> E2EVerificationResult:
    """Create a Job and verify the real calculation/drawing/BIM path.

    When ``reviewer`` is supplied every current artifact is explicitly approved. When
    ``publisher`` is supplied, ``reviewer`` is mandatory and the authoritative OS publish
    gate is exercised as well.
    """
    project_id = project_id.strip()
    job_code = job_code.strip()
    if not project_id or not job_code:
        raise ValueError("project_id and job_code must not be empty")
    if publisher and not reviewer:
        raise ValueError("publisher requires reviewer; publishing may not bypass engineering review")

    readiness = client.readiness()
    if not readiness.ready:
        raise RuntimeError("AI-Engineering-OS is not ready")
    project = client.get_project(project_id)
    if project.get("id") != project_id:
        raise RuntimeError("AI-Engineering-OS returned inconsistent project identity")

    component_id = str(column.get("component_id", "")).strip()
    if not component_id:
        raise ValueError("column component_id must not be empty")
    job = client.create_job(
        project_id=project_id,
        code=job_code,
        name=f"RC 柱 E2E 驗證 {component_id}",
        user_request="OpenWorker E6.4 真實 RC 柱 calculation + drawing + BIM 端到端驗證",
        expected_deliverables=["calculation", "drawing", "bim_ifc"],
        metadata={"verification": "openworker-e6.4/rc-column", "component_id": component_id},
    )
    job_id = _required_text(job, "id", "created Job")

    flow: ManagedRCFlowResult = execute_managed_rc_column(client, job_id=job_id, column=column)
    # The managed flow is authoritative for the post-execution Job state. Keeping
    # the create_job() snapshot here would incorrectly report ``draft`` even when
    # the real calculation/drawing/BIM path has transitioned the Job to review.
    job = flow.job
    approval: dict[str, Any] | None = None
    delivery: dict[str, Any] | None = None

    if reviewer:
        for artifact in flow.artifacts:
            client.submit_artifact_review(
                job_id=job_id,
                artifact_id=_required_text(artifact, "id", "RC flow Artifact"),
                reviewer=reviewer,
                decision="approved",
                comment="OpenWorker E6.4 E2E verification approval",
            )
        approval = client.approval_status(job_id)
        if approval.get("approved") is not True:
            raise RuntimeError("E2E review phase did not approve every current artifact revision")
        job = client.get_job(job_id)
        if job.get("status") != "completed":
            raise RuntimeError("approved E2E Job did not transition to completed")

    if publisher:
        publish = client.publish_job(
            job_id=job_id,
            publisher=publisher,
            note="OpenWorker E6.4 E2E verification publish",
        )
        delivery = publish["delivery"]
        job = client.get_job(job_id)
        if job.get("status") != "published":
            raise RuntimeError("published E2E Job did not transition to published")

    return E2EVerificationResult(
        project_id=project_id,
        job=job,
        artifacts=flow.artifacts,
        approval_status=approval,
        delivery=delivery,
        digital_thread=flow.digital_thread,
    )


def _required_text(payload: Mapping[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{context} missing required field: {key}")
    return value.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the real OpenWorker RC-column E2E verification path")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--job-code", default="")
    parser.add_argument("--component-id", default="E2E-C1")
    parser.add_argument("--width-mm", type=float, default=600)
    parser.add_argument("--depth-mm", type=float, default=600)
    parser.add_argument("--clear-height-mm", type=float, default=3500)
    parser.add_argument("--concrete-grade", default="C35")
    parser.add_argument("--steel-grade", default="HRB400")
    parser.add_argument("--axial-force-kn", type=float, default=1800)
    parser.add_argument("--moment-x-knm", type=float, default=220)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--publisher", default="")
    parser.add_argument("--confirm-side-effects", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.confirm_side_effects:
        raise SystemExit("Refusing to create engineering records without --confirm-side-effects")
    code = args.job_code.strip() or "OW-E2E-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    column = {
        "component_id": args.component_id,
        "width_mm": args.width_mm,
        "depth_mm": args.depth_mm,
        "clear_height_mm": args.clear_height_mm,
        "concrete_grade": args.concrete_grade,
        "steel_grade": args.steel_grade,
        "axial_force_kn": args.axial_force_kn,
        "moment_x_knm": args.moment_x_knm,
        "ifc_schema": "IFC4",
    }
    client = EngineeringOSFlowClient(EngineeringOSConfig(base_url=args.base_url, timeout_seconds=1800))
    result = run_rc_column_e2e(
        client,
        project_id=args.project_id,
        job_code=code,
        column=column,
        reviewer=args.reviewer.strip() or None,
        publisher=args.publisher.strip() or None,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
