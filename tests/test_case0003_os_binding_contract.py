from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_os_artifact_submit_requires_current_render_acceptance_and_v2_binding():
    text = read("case0003_local_os_artifacts.ps1")
    assert "acceptance\\render\\render-acceptance.json" in text
    assert "artifact-ingest/v2" in text
    assert "render_fingerprint" in text
    assert "blender_fingerprint" in text
    assert "scenex_fingerprint" in text


def test_os_binding_guard_runs_before_controller():
    text = read("case0003_local_continue_auto.ps1")
    guard = text.index("& $osArtifactGuard")
    controller = text.index("& $controller")
    assert guard < controller
    assert "case0003-root-resolution/v11" in text


def test_os_delivery_requires_v2_semantic_binding():
    text = read("case0003_local_os_delivery.ps1")
    assert "semantic_contract_version" in text
    assert "engineering-os-artifact-ingest-receipt/v2" in text
    assert "OS artifact ingest is stale relative to current render acceptance" in text
