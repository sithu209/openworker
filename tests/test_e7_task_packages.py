from __future__ import annotations

import pytest

from coworker.personas.task_package import (
    ActionClass,
    TaskPackageError,
    WorkStep,
    company_task_package,
    media_task_package,
)


def test_media_package_is_declarative_and_canonical_generation_is_not_openworker_owned() -> None:
    package = media_task_package(
        title="H3 launch clip",
        brief="Create a short product clip from approved source assets.",
        inputs=["inputs/brief.md", "inputs/reference.png"],
        deliverables=["deliverables/final.mp4"],
    )
    data = package.to_dict()
    assert data["schema"] == "openworker.persona-task-package/v1"
    assert data["kind"] == "media"
    produce = next(step for step in package.steps if step.id == "produce")
    assert produce.action is ActionClass.CANONICAL
    assert produce.authority != "openworker"
    assert package.has_external_actions is False


def test_media_publish_is_explicit_external_and_requires_approval() -> None:
    package = media_task_package(
        title="Approved campaign",
        brief="Prepare the approved media package.",
        publish_target="social:brand-channel",
    )
    publish = next(step for step in package.steps if step.id == "publish")
    assert publish.action is ActionClass.EXTERNAL
    assert publish.requires_approval is True
    assert package.has_external_actions is True


def test_company_package_routes_specialist_handoffs_to_existing_authorities() -> None:
    package = company_task_package(
        title="Bridge proposal",
        brief="Prepare a proposal grounded in supplied project evidence.",
        needs_engineering=True,
        needs_media=True,
    )
    authorities = {step.id: step.authority for step in package.steps}
    assert authorities["engineering-handoff"] == "AI-Engineering-OS"
    assert "specialist media engine" in authorities["media-handoff"]
    assert package.has_external_actions is False


def test_company_external_send_is_never_implicit() -> None:
    draft = company_task_package(title="Client update", brief="Draft an evidence-backed update.")
    assert all(step.id != "external-send" for step in draft.steps)

    send = company_task_package(
        title="Client update",
        brief="Prepare an evidence-backed update for approval.",
        external_target="email:client@example.test",
    )
    external = next(step for step in send.steps if step.id == "external-send")
    assert external.requires_approval is True


def test_external_step_without_approval_fails_closed() -> None:
    with pytest.raises(TaskPackageError, match="require approval"):
        WorkStep(
            "unsafe",
            "Send without approval",
            action=ActionClass.EXTERNAL,
            authority="connector",
            requires_approval=False,
        )


def test_canonical_step_cannot_claim_openworker_as_execution_authority() -> None:
    with pytest.raises(TaskPackageError, match="downstream authority"):
        WorkStep(
            "unsafe",
            "Pretend OpenWorker is the professional engine",
            action=ActionClass.CANONICAL,
        )
