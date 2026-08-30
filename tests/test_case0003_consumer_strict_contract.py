from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_consumer_quarantine_binds_both_upstream_stage_receipts():
    src = text("scripts/case0003_quarantine_stale_consumer.ps1")
    assert "consumer-workspace/v2" in src
    assert "imagery_identity_mismatch" in src
    assert "terrain_manifest_identity_mismatch" in src
    assert "terrain_acceptance_identity_mismatch" in src
    assert "artifact_identity_" in src
    assert ".openworker\\quarantine\\consumer" in src


def test_auto_quarantine_order_is_upstream_to_downstream():
    src = text("scripts/case0003_local_continue_auto.ps1")
    imagery = src.index("& $imageryQuarantine")
    terrain = src.index("& $terrainQuarantine")
    consumer = src.index("& $consumerQuarantine")
    controller = src.index("& $controller")
    assert imagery < terrain < consumer < controller
    assert "openworker/case0003-root-resolution/v9" in src
