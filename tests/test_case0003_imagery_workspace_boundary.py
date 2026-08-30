from pathlib import Path

import pytest

from scripts.case0003_record_imagery_acceptance import ImageryAcceptanceError, within


def test_imagery_acceptance_rejects_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"not-empty")
    with pytest.raises(ImageryAcceptanceError, match="escapes canonical workspace"):
        within(workspace.resolve(), outside, "Street View 0")


def test_imagery_acceptance_allows_path_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    image = workspace / "streetview" / "browser" / "0.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"not-empty")
    assert within(workspace.resolve(), image, "Street View 0") == image.resolve()


def test_auto_entrypoint_quarantines_unsafe_imagery_before_controller() -> None:
    auto = Path("scripts/case0003_local_continue_auto.ps1").read_text(encoding="utf-8")
    quarantine = Path("scripts/case0003_quarantine_unsafe_imagery.ps1").read_text(encoding="utf-8")
    assert "case0003_quarantine_unsafe_imagery.ps1" in auto
    assert auto.index("& $quarantine") < auto.index("& $controller")
    assert ".openworker\\quarantine\\imagery" in quarantine
    assert "Move-Item" in quarantine
    assert "escapes workspace" in quarantine
