from __future__ import annotations

from pathlib import Path


def test_openworker_inventory_exposes_case0003_authority_roots():
    root = Path(__file__).resolve().parents[1]
    inventory = (root / "go-runtime" / "internal" / "inventory" / "inventory.go").read_text(encoding="utf-8")
    for env_name in (
        "OPENWORKER_ROOT",
        "GO_TOOL_ROOT",
        "TERRAIN_ROOT",
        "SCENEX_ROOT",
        "ENGINEERING_OS_ROOT",
        "OPENWORKER_REVIEW_DRIVE_ROOT",
    ):
        assert env_name in inventory
    assert "os.Stat(r.Path)" in inventory
    assert "info.IsDir()" in inventory


def test_case0003_auto_controller_uses_inventory_before_environment_and_job_binding_identity():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "case0003_local_continue_auto.ps1").read_text(encoding="utf-8")
    assert "/v1/node/status" in script
    assert "node.inventory.roots" in script
    assert "explicit>openworker-inventory>environment" in script
    assert "OPENWORKER_REVIEW_DRIVE_ROOT" in script
    assert ".openworker\\job-binding.json" in script
    assert "openworker.job-binding.v1" in script
    assert "$binding.project_id" in script
    assert "$binding.job_id" in script
    assert "JobBinding host mismatch" in script
    assert "JobBinding workspace mismatch" in script
    assert "explicit OSProjectId does not match JobBinding project_id" in script
    assert "explicit OSJobId does not match JobBinding job_id" in script
    assert "openworker/case0003-root-resolution/v3" in script


def test_case0003_auto_controller_still_delegates_to_canonical_physical_gate_controller():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "case0003_local_continue_auto.ps1").read_text(encoding="utf-8")
    assert "case0003_local_continue.ps1" in script
    assert "-OSProjectId $OSProjectId" in script
    assert "-OSJobId $OSJobId" in script
    assert "-DriveSyncRoot $DriveSyncRoot" in script
    assert "-TerrainRoot $TerrainRoot" in script
    assert "-SceneXRoot $SceneXRoot" in script
