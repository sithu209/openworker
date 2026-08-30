from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker.engineering.digital_thread import EvidenceKind, EvidenceRef
from coworker.personas.product_contract import (
    HandoffCapability,
    PersonaSession,
    ProductContractError,
    QAStatus,
    build_product_plan,
    canonical_handoffs,
    delivery_evidence,
    external_approval_intents,
    save_task_package,
)
from coworker.personas.task_package import company_task_package, media_task_package


def test_media_session_persists_task_package_inside_project_workspace(tmp_path: Path) -> None:
    session = PersonaSession(persona="media", session_id="session-001", workspace_id="project-a")
    package = media_task_package(
        title="Launch clip",
        brief="Create a short clip using supplied source material.",
        inputs=["inputs/brief.md"],
        deliverables=["deliverables/final.mp4"],
    )

    relative = save_task_package(tmp_path, session, package, package_id="launch-clip")
    path = tmp_path / relative

    assert relative == ".openworker/persona-tasks/media/session-001/launch-clip.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "openworker.persona-workspace-task/v1"
    assert payload["session"]["workspace_id"] == "project-a"
    assert payload["task_package"]["kind"] == "media"


def test_workspace_persistence_rejects_kind_mismatch_and_path_injection(tmp_path: Path) -> None:
    package = media_task_package(title="Media", brief="Brief")
    with pytest.raises(ProductContractError, match="must match"):
        save_task_package(
            tmp_path,
            PersonaSession(persona="company", session_id="s1", workspace_id="w1"),
            package,
            package_id="p1",
        )

    with pytest.raises(ProductContractError, match="safe workspace identifier"):
        PersonaSession(persona="media", session_id="../escape", workspace_id="w1")

    with pytest.raises(ProductContractError, match="safe workspace identifier"):
        save_task_package(
            tmp_path,
            PersonaSession(persona="media", session_id="s1", workspace_id="w1"),
            package,
            package_id="../../escape",
        )


def test_media_canonical_handoff_goes_through_ai_engineering_os() -> None:
    package = media_task_package(title="Media", brief="Brief")
    handoffs = canonical_handoffs(package, task_package_path=".openworker/task.json")

    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert handoff.step_id == "produce"
    assert handoff.capability is HandoffCapability.MEDIA
    assert handoff.authority == "AI-Engineering-OS"
    assert "specialist media engine" in handoff.source_authority
    assert handoff.metadata["execution"] == "descriptor-only"


def test_company_engineering_and_media_handoffs_share_canonical_control_plane() -> None:
    package = company_task_package(
        title="Bridge campaign",
        brief="Prepare engineering and media delivery work.",
        needs_engineering=True,
        needs_media=True,
    )
    handoffs = {item.step_id: item for item in canonical_handoffs(package)}

    assert handoffs["engineering-handoff"].authority == "AI-Engineering-OS"
    assert handoffs["engineering-handoff"].capability is HandoffCapability.ENGINEERING
    assert handoffs["media-handoff"].authority == "AI-Engineering-OS"
    assert handoffs["media-handoff"].capability is HandoffCapability.MEDIA


def test_external_actions_remain_approval_metadata_only() -> None:
    package = company_task_package(
        title="Client update",
        brief="Prepare an approved client update.",
        external_target="email:client@example.test",
    )
    intents = external_approval_intents(package)

    assert len(intents) == 1
    assert intents[0].requires_approval is True
    data = intents[0].to_dict()
    assert data["execution"] == "not-performed"
    assert data["requires_approval"] is True


def test_product_plan_reuses_existing_scheduler_connector_and_artifact_layers(tmp_path: Path) -> None:
    package = media_task_package(
        title="Campaign",
        brief="Produce media and prepare approval metadata.",
        publish_target="social:brand",
    )
    plan = build_product_plan(
        tmp_path,
        PersonaSession(persona="media", session_id="s1", workspace_id="w1"),
        package,
        package_id="campaign",
    )
    data = plan.to_dict()

    assert data["schema"] == "openworker.persona-product-plan/v1"
    assert data["bindings"]["scheduler"].startswith("coworker.automation")
    assert data["bindings"]["connectors"].startswith("coworker.connectors")
    assert "AI-Engineering-OS Artifact Registry" in data["bindings"]["artifacts"]
    assert data["handoffs"][0]["authority"] == "AI-Engineering-OS"
    assert data["external_approval_intents"][0]["execution"] == "not-performed"


def test_delivery_evidence_requires_real_artifacts_before_passed_qa() -> None:
    with pytest.raises(ProductContractError, match="at least one real artifact"):
        delivery_evidence([], qa_status=QAStatus.PASSED)

    artifact = EvidenceRef(
        system="ai-engineering-os",
        kind=EvidenceKind.ARTIFACT,
        identifier="artifact-1",
        checksum="sha256:abc",
        uri="workspace://deliverables/final.mp4",
        media_type="video/mp4",
    )
    evidence = delivery_evidence(
        [artifact],
        qa_status=QAStatus.PASSED,
        qa_notes=["duration checked", "artifact opens"],
        delivery_ready=True,
    )
    data = evidence.to_dict()
    assert data["delivery_ready"] is True
    assert data["external_delivery_performed"] is False
    assert data["artifacts"][0]["checksum"] == "sha256:abc"


def test_delivery_ready_cannot_bypass_qa() -> None:
    artifact = EvidenceRef(
        system="ai-engineering-os",
        kind=EvidenceKind.ARTIFACT,
        identifier="artifact-1",
        checksum="sha256:abc",
    )
    with pytest.raises(ProductContractError, match="requires QAStatus.PASSED"):
        delivery_evidence([artifact], qa_status=QAStatus.PENDING, delivery_ready=True)
