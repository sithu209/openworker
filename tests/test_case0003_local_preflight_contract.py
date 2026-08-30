from pathlib import Path


def test_case0003_auto_continue_runs_preflight_before_controller():
    root = Path(__file__).resolve().parents[1]
    auto = (root / "scripts" / "case0003_local_continue_auto.ps1").read_text(encoding="utf-8")
    preflight = (root / "scripts" / "case0003_local_preflight.ps1").read_text(encoding="utf-8")
    registry = (root / "scripts" / "openworker_set_machine_roots.ps1").read_text(encoding="utf-8")

    assert "case0003_local_preflight.ps1" in auto
    assert auto.index("& $preflight") < auto.index("& $controller")
    assert "openworker/case0003-root-resolution/v4" in auto
    assert "openworker/case0003-local-preflight/v1" in preflight
    assert "dtm_catalog.sqlite" in preflight
    assert "job-binding.json" in preflight
    assert "/healthz" in preflight
    assert "OPENWORKER_MACHINE_ROOTS_FILE" in registry
    assert "machine-roots.json" in registry
