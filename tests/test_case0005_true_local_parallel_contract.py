from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _worklist() -> dict:
    return json.loads((ROOT / "case-worklists" / "0005.json").read_text(encoding="utf-8"))


def test_activation_uses_canonical_operational_supervisor() -> None:
    text = (ROOT / "scripts" / "activate-case0005-local-supervisor.ps1").read_text(encoding="utf-8")
    assert "coworker.case0005_verified_local_controller" in text
    assert "install-and-verify-true-local-supervisor.ps1" in text
    assert "/api/execution/local-supervisor/status" in text
    assert "fresh_claim_slot_count" in text
    assert "fresh_executor_slot_count" in text
    assert "OPERATIONAL" in text
    assert "verify-gtr-local-supervisor.ps1" not in text
    assert "controllerModule = 'coworker.case0005_local_supervisor'" not in text


def test_activation_cannot_skip_real_verification_or_reuse_unknown_old_binaries() -> None:
    text = (ROOT / "scripts" / "activate-case0005-local-supervisor.ps1").read_text(encoding="utf-8")
    assert "SkipParallelVerification" not in text
    assert "binaries_reinstalled_from_current_checkout=$true" in text
    assert "install-and-verify-true-local-supervisor.ps1" in text
    assert "REAL_VERIFIED" in text
    assert "registered_capabilities" in text
    assert "required_case_capabilities" in text
    assert "capability_coverage_complete=$true" in text
    for capability in (
        "comfyx-studio.director.preproduction",
        "comfyx-studio.storyboard.plan",
        "presentation.openmaic",
        "openworker.case.publish-artifacts",
        "openworker.review.await-drive",
        "image.comfyx.storyboard-real",
        "comfyx-studio.storyboard.real-bind",
        "comfyx.production.video.real",
        "comfyx-studio.finalize",
        "openworker.workledger.revision",
        "engineering_os.case0005.identity",
        "engineering_os.artifact.register",
        "engineering_os.delivery.publish",
        "openworker.delivery.validate",
        "drive.review.publish",
    ):
        assert capability in text


def test_case0005_worklist_requires_live_four_plus_four_and_queue_owned_fanout() -> None:
    worklist = _worklist()
    policy = worklist["parallel_policy"]
    assert policy["canonical_controller_module"] == "coworker.case0005_verified_local_controller"
    assert policy["required_supervisor_status"] == "OPERATIONAL"
    assert policy["required_verification_status"] == "REAL_VERIFIED"
    assert policy["required_fresh_claim_slots"] == 4
    assert policy["required_fresh_executor_slots"] == 4
    assert policy["max_local_slots"] == 4
    assert policy["fanout_queue_owner"] == "go-tool-runtime:8848"
    assert policy["openworker_business_child_jobs_allowed"] is False
    assert policy["github_actions_business_execution_allowed"] is False
    assert policy["github_actions_fallback_allowed"] is False
    assert policy["review_receipt_capability"] == "openworker.review.await-drive"
    assert policy["review_receipt_cloud_command_ingress_allowed"] is False


def test_drive_review_gates_are_real_local_supervisor_work_items() -> None:
    steps = {step["step_id"]: step for step in _worklist()["steps"]}
    for step_id, dependency in (("0005-027", "0005-026"), ("0005-057", "0005-056"), ("0005-100", "0005-090")):
        step = steps[step_id]
        assert step["kind"] == "work"
        assert step["dependencies"] == [dependency]
        assert step["allowed_actions"] == ["openworker.review.await-drive"]
    assert steps["0005-027"]["acceptance"] == ["approved_storyboard_pptx_sha256", "approval_decision", "approval_receipt"]
    assert steps["0005-057"]["acceptance"] == ["approved_illustrated_storyboard_sha256", "approval_decision", "approval_receipt"]
    assert steps["0005-100"]["acceptance"] == ["review_receipt", "review_decision", "accepted_revision_id"]


def test_reviewable_artifacts_must_be_drive_visible_with_cloud_identity() -> None:
    steps = {step["step_id"]: step for step in _worklist()["steps"]}
    for step_id in ("0005-026", "0005-056", "0005-090"):
        step = steps[step_id]
        assert step["allowed_actions"] == ["openworker.case.publish-artifacts"]
        acceptance = set(step["acceptance"])
        for key in (
            "published_artifact_sha256",
            "drive_folder_id",
            "drive_revision_web_view_link",
            "drive_file_ids",
            "drive_file_links",
            "transport",
            "chatgpt_review_ready",
            "github_action_used_for_artifact_transport",
        ):
            assert key in acceptance


def test_finalizer_and_final_review_require_physical_contact_sheet() -> None:
    steps = {step["step_id"]: step for step in _worklist()["steps"]}
    final_acceptance = set(steps["0005-070"]["acceptance"])
    assert "review_contact_sheet" in final_acceptance
    assert "review_contact_sheet_sha256" in final_acceptance
    assert "visual contact sheet" in steps["0005-090"]["title"]
    controller = (ROOT / "coworker" / "case0005_verified_local_controller.py").read_text(encoding="utf-8")
    assert '"final/review-contact-sheet.jpg"' in controller
    mapper = (ROOT / "coworker" / "case0005_artifact_publish_acceptance.py").read_text(encoding="utf-8")
    assert 'final/review-contact-sheet.jpg' in mapper
    assert "len(relpaths) != 3" in mapper


def test_lifecycle_has_one_action_per_automatic_step() -> None:
    steps = {step["step_id"]: step for step in _worklist()["steps"]}
    for step_id in ("0005-080", "0005-082", "0005-085", "0005-090", "0005-100", "0005-110", "0005-120"):
        assert len(steps[step_id]["allowed_actions"]) == 1
    assert steps["0005-080"]["allowed_actions"] == ["openworker.workledger.revision"]
    assert steps["0005-082"]["allowed_actions"] == ["engineering_os.case0005.identity"]
    assert steps["0005-085"]["allowed_actions"] == ["engineering_os.artifact.register"]
    assert steps["0005-110"]["allowed_actions"] == ["engineering_os.delivery.publish"]
    assert steps["0005-120"]["allowed_actions"] == ["openworker.delivery.validate"]


def test_artifact_and_lifecycle_mixins_are_wired_into_canonical_controller() -> None:
    text = (ROOT / "coworker" / "case0005_verified_local_controller.py").read_text(encoding="utf-8")
    assert "Case0005ArtifactPublishAcceptanceMixin" in text
    assert "Case0005LifecycleMixin" in text
    assert "timeout_sec=86400 if action==_REVIEW_GATE_ACTION" in text
    mapper = (ROOT / "coworker" / "case0005_artifact_publish_acceptance.py").read_text(encoding="utf-8")
    assert "google-drive-api" in mapper
    assert "github_action_used_for_artifact_transport" in mapper
    assert "presentation/storyboard-text-only.pptx" in mapper
    assert "presentation/storyboard-illustrated.pptx" in mapper


def test_case_spec_forbids_cloud_command_ingress_and_requires_roundtrip() -> None:
    spec = json.loads((ROOT / "case-specs" / "0005.json").read_text(encoding="utf-8"))
    approval = spec["approval_artifact_return"]
    assert approval["review_gate_capability"] == "openworker.review.await-drive"
    assert approval["cloud_command_ingress_allowed"] is False
    assert set(approval["review_receipt_command_fields_forbidden"]) == {"command", "commands", "tool"}
    assert "final/review-contact-sheet.jpg" in approval["final_review_required_artifacts"]
    assert approval["final_review_pass_requires_workledger_accept"] is True
    assert approval["final_review_pass_requires_engineering_os_artifact_approval"] is True
    assert approval["final_delivery_validation_requires_review_provenance"] is True
    assert spec["execution_policy"]["success_requires_chatgpt_review_receipt_roundtrip"] is True
