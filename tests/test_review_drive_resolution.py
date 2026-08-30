from __future__ import annotations

from pathlib import Path

import pytest

from coworker.review_cycle import DEFAULT_DRIVE_FOLDER_NAME, ReviewCycle, ReviewCycleError


def test_explicit_drive_root_wins(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = tmp_path / "drive"
    root.mkdir()
    cycle = ReviewCycle(workspace)
    assert cycle.resolve_drive_sync_root(root) == root.resolve()


def test_missing_explicit_drive_root_fails_closed(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cycle = ReviewCycle(workspace)
    with pytest.raises(ReviewCycleError, match="sync root unavailable"):
        cycle.resolve_drive_sync_root(tmp_path / "missing")


def test_drive_folder_name_is_stable_contract():
    assert DEFAULT_DRIVE_FOLDER_NAME == "OpenWorker-ChatGPT-Review-TEMP"


def test_handoff_uses_exact_explicit_review_folder(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bundle = workspace / ".openworker" / "reviews" / "rev_1"
    (bundle / "artifacts").mkdir(parents=True)
    (bundle / "review-request.json").write_text("{}", encoding="utf-8")
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    (bundle / "artifacts" / "render.png").write_bytes(b"render")
    drive = tmp_path / DEFAULT_DRIVE_FOLDER_NAME
    drive.mkdir()
    cycle = ReviewCycle(workspace)
    target = cycle.handoff_to_drive_sync(bundle, drive_sync_root=drive, work_code="OWJ-1")
    assert target == (drive / "OWJ-1" / "rev_1").resolve()
    assert (target / "artifacts" / "render.png").read_bytes() == b"render"
