from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coworker.case0005_verified_local_controller import (
    _CANONICAL_MODULE,
    VerifiedLocalCase0005Controller,
)


def _controller(tmp_path: Path) -> VerifiedLocalCase0005Controller:
    controller = object.__new__(VerifiedLocalCase0005Controller)
    controller.workspace = tmp_path / "workspace"
    controller.openworker_root = tmp_path / "openworker"
    controller._localexec_env = lambda: {}
    controller._safe_id = lambda value: str(value).replace("/", "-")
    return controller


def _assert_canonical(payload: dict) -> None:
    command = str(payload["command"])
    assert _CANONICAL_MODULE in command
    assert "coworker.case0005_logged_controller" not in command
    assert "coworker.case0005_true_local_controller" not in command
    assert payload["dispatch_id"].startswith("verified-local-controller-")


def test_ordinary_child_is_forced_through_verified_controller(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    worklist = SimpleNamespace(case_id="0005", assigned_host="DESKTOP-ODAQN0D")
    step = SimpleNamespace(step_id="0005-010", kind="work")
    payload = controller._job_payload(worklist, step, "comfyx-studio.director.preproduction", "case0005-010-x", tmp_path / "claim.json")
    _assert_canonical(payload)


def test_image_child_is_forced_through_verified_controller(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    worklist = SimpleNamespace(case_id="0005", assigned_host="DESKTOP-ODAQN0D")
    payload = controller._image_child_payload(
        worklist=worklist,
        step_id="0005-030",
        group_id="group-image",
        child_id="case0005-image-001",
        asset_id="snow-white",
        role="character_master",
        claim_path=tmp_path / "claim.json",
        manifest_path=tmp_path / "manifest.json",
    )
    _assert_canonical(payload)


def test_video_child_is_forced_through_verified_controller(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    worklist = SimpleNamespace(case_id="0005", assigned_host="DESKTOP-ODAQN0D")
    payload = controller._video_child_payload(
        worklist=worklist,
        group_id="group-video",
        child_id="case0005-video-001",
        shot_id="shot-001",
        claim_path=tmp_path / "claim.json",
        manifest_path=tmp_path / "manifest.json",
    )
    _assert_canonical(payload)
