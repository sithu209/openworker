from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_auto_quarantines_render_outputs_before_controller():
    text = (ROOT / "scripts" / "case0003_local_continue_auto.ps1").read_text(encoding="utf-8")
    q = text.index("& $renderQuarantine")
    c = text.index("& $controller")
    assert q < c
    assert "openworker/case0003-root-resolution/v10" in text


def test_render_quarantine_requires_current_upstream_fingerprints():
    text = (ROOT / "scripts" / "case0003_quarantine_stale_render_outputs.ps1").read_text(encoding="utf-8")
    assert "blender-workspace/v2" in text
    assert "consumer fingerprint mismatch" in text
    assert "scenex-workspace-browse/v2" in text
    assert "terrain fingerprint mismatch" in text
    assert "terrain manifest SHA mismatch" in text
    assert "GEO SHA mismatch" in text


def test_render_recorder_is_progress_only():
    text = (ROOT / "scripts" / "case0003_record_render_acceptance.py").read_text(encoding="utf-8")
    assert 'kind="progress"' in text
    assert 'ledger.set_revision_status(rid, "verifying"' in text
    assert "ledger.accept_revision(" not in text
    assert "ledger.deliver_revision(" not in text
    assert "openworker-case0003-render-acceptance/v1" in text
