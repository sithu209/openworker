from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_terrain_quarantine_requires_v2_and_identity_hashes():
    src = text("scripts/case0003_quarantine_stale_terrain.ps1")
    assert "terrain-aoi-workspace/v2" in src
    assert "geo_sha_mismatch" in src
    assert "catalog_sha_mismatch" in src
    assert "request_sha_mismatch" in src
    assert "artifact_sha_" in src
    assert ".openworker\\quarantine\\terrain" in src
    assert "Move-Item -LiteralPath $terrainRoot" in src


def test_auto_runs_strict_terrain_quarantine_before_controller():
    src = text("scripts/case0003_local_continue_auto.ps1")
    quarantine = src.index("& $terrainQuarantine")
    controller = src.index("& $controller")
    assert quarantine < controller
    assert "openworker/case0003-root-resolution/v8" in src
    assert "case0003_record_terrain_acceptance.py" in src


def test_terrain_recorder_is_progress_only_not_whole_case_acceptance():
    src = text("scripts/case0003_record_terrain_acceptance.py")
    assert '"terrain-aoi-workspace/v2"' in src
    assert 'kind="progress"' in src
    assert 'ledger.set_revision_status(rid, "verifying"' in src
    assert "ledger.accept_revision(" not in src
    assert "ledger.deliver_revision(" not in src
    assert '"accepted_revision_id": ""' in src
    assert '"delivered_revision_id": ""' in src
