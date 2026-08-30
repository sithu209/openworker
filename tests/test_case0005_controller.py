from pathlib import Path

import pytest

from coworker.case0005_controller import Case0005Controller
from coworker.case_worklist import CaseStep, CaseWorklist, CaseWorklistError


def _worklist(tmp_path: Path) -> CaseWorklist:
    return CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[],
    )


def test_role_claims_for_parallel_character_and_scene_branches(tmp_path: Path):
    controller = Case0005Controller(tmp_path)
    worklist = _worklist(tmp_path)
    character = CaseStep(
        step_id="0005-030",
        title="characters",
        kind="fanout",
        allowed_actions=["image.comfyx.storyboard-real"],
        acceptance=["character_receipts", "character_images", "character_sha256"],
    )
    scene = CaseStep(
        step_id="0005-040",
        title="scenes",
        kind="fanout",
        allowed_actions=["image.comfyx.storyboard-real"],
        acceptance=["scene_receipts", "scene_images", "scene_sha256"],
    )

    assert controller._claim_inputs(worklist, character, "image.comfyx.storyboard-real", {}) == {
        "workspace_root": str(tmp_path.resolve()),
        "assigned_host": "DESKTOP-ODAQN0D",
        "role": "character_master",
        "requirements_relpath": "visual-assets/requirements.json",
    }
    assert controller._claim_inputs(worklist, scene, "image.comfyx.storyboard-real", {})["role"] == "scene_concept"


def test_character_batch_acceptance_maps_real_receipts(tmp_path: Path):
    controller = Case0005Controller(tmp_path)
    step = CaseStep(
        step_id="0005-030",
        title="characters",
        kind="fanout",
        allowed_actions=["image.comfyx.storyboard-real"],
        acceptance=["character_receipts", "character_images", "character_sha256"],
    )
    result = {
        "status": "completed",
        "capability_id": "image.comfyx.storyboard-real",
        "evidence": {
            "role": "character_master",
            "receipts": [{"status": "succeeded"}, {"status": "succeeded"}],
            "images": [r"D:\AI-Work\jobs\0005-SNOW-WHITE\visual-assets\characters\snow-white\master.png", r"D:\AI-Work\jobs\0005-SNOW-WHITE\visual-assets\characters\queen\master.png"],
            "sha256": ["a" * 64, "b" * 64],
        },
    }
    evidence = controller._acceptance_evidence(step, result)
    assert len(evidence["character_receipts"]) == 2
    assert len(evidence["character_images"]) == 2
    assert evidence["character_sha256"] == ["a" * 64, "b" * 64]


def test_scene_batch_acceptance_requires_matching_arrays(tmp_path: Path):
    controller = Case0005Controller(tmp_path)
    step = CaseStep(
        step_id="0005-040",
        title="scenes",
        kind="fanout",
        allowed_actions=["image.comfyx.storyboard-real"],
        acceptance=["scene_receipts", "scene_images", "scene_sha256"],
    )
    result = {
        "status": "completed",
        "capability_id": "image.comfyx.storyboard-real",
        "evidence": {
            "role": "scene_concept",
            "receipts": [{"status": "succeeded"}],
            "images": [r"D:\AI-Work\jobs\0005-SNOW-WHITE\visual-assets\scene-bibles\forest\concept.png"],
            "sha256": ["c" * 64],
        },
    }
    evidence = controller._acceptance_evidence(step, result)
    assert evidence["scene_sha256"] == ["c" * 64]


def test_atomic_shot_real_bind_claim_and_acceptance(tmp_path: Path):
    controller = Case0005Controller(tmp_path)
    worklist = _worklist(tmp_path)
    step = CaseStep(
        step_id="0005-050",
        title="shot join",
        kind="work",
        dependencies=["0005-030", "0005-040"],
        allowed_actions=["comfyx-studio.storyboard.real-bind"],
        acceptance=["shot_image_receipts", "shot_images", "shot_image_sha256", "bound_storyboard_request"],
    )
    inputs = controller._claim_inputs(worklist, step, "comfyx-studio.storyboard.real-bind", {})
    assert inputs["request_relpath"] == "presentation/storyboard-request.json"
    assert inputs["output_relpath"] == "presentation/storyboard-request.bound.json"

    result = {
        "status": "completed",
        "capability_id": "comfyx-studio.storyboard.real-bind",
        "evidence": {
            "shot_image_receipts": [{"status": "succeeded"}],
            "shot_images": [r"D:\AI-Work\jobs\0005-SNOW-WHITE\visual-assets\shots\shot-001.png"],
            "shot_image_sha256": ["d" * 64],
            "bound_request": r"D:\AI-Work\jobs\0005-SNOW-WHITE\presentation\storyboard-request.bound.json",
            "bind_receipt": r"D:\AI-Work\jobs\0005-SNOW-WHITE\evidence\storyboard-bind-receipt.json",
        },
    }
    evidence = controller._acceptance_evidence(step, result)
    assert evidence["shot_image_sha256"] == ["d" * 64]
    assert evidence["bound_storyboard_request"].endswith("storyboard-request.bound.json")


def test_child_job_keeps_case0005_controller(tmp_path: Path):
    controller = Case0005Controller(tmp_path)
    worklist = _worklist(tmp_path)
    step = CaseStep(
        step_id="0005-030",
        title="characters",
        kind="fanout",
        allowed_actions=["image.comfyx.storyboard-real"],
        acceptance=["character_receipts"],
    )
    claim = tmp_path / "claim.json"
    payload = controller._job_payload(worklist, step, "image.comfyx.storyboard-real", "case0005-test", claim)
    assert "coworker.case0005_controller" in payload["command"]
    assert "github" not in payload["command"].lower()


def test_storyboard_plan_rejects_director_provenance_drift(tmp_path: Path, monkeypatch):
    controller = Case0005Controller(tmp_path)
    parent = CaseStep(
        step_id="0005-010",
        title="director",
        allowed_actions=["comfyx-studio.director.preproduction"],
        acceptance=["director_plan_sha256"],
        evidence={"director_plan_sha256": "a" * 64},
    )
    worklist = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[parent],
    )
    monkeypatch.setattr(controller.runtime, "load", lambda: worklist)
    step = CaseStep(
        step_id="0005-020",
        title="storyboard plan",
        allowed_actions=["comfyx-studio.storyboard.plan"],
        acceptance=["storyboard_request"],
    )
    result = {
        "status": "completed",
        "capability_id": "comfyx-studio.storyboard.plan",
        "evidence": {"director_plan_sha256": "b" * 64, "storyboard_request": "x"},
    }
    with pytest.raises(CaseWorklistError, match="Director provenance mismatch"):
        controller._acceptance_evidence(step, result)


def test_text_storyboard_rejects_wrong_consumed_request_sha(tmp_path: Path):
    controller = Case0005Controller(tmp_path)
    request = tmp_path / "presentation" / "storyboard-request.json"
    request.parent.mkdir(parents=True)
    request.write_text('{"title":"Snow White","slides":[{"title":"S1"}]}\n', encoding="utf-8")
    step = CaseStep(
        step_id="0005-025",
        title="text storyboard",
        allowed_actions=["presentation.openmaic"],
        acceptance=["storyboard_pptx"],
    )
    result = {
        "status": "completed",
        "capability_id": "presentation.openmaic",
        "evidence": {"request_sha256": "0" * 64},
    }
    with pytest.raises(CaseWorklistError, match="request provenance mismatch"):
        controller._acceptance_evidence(step, result)
