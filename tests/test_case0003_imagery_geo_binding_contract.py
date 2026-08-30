from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_case0003_controller_binds_imagery_to_current_geo():
    text = (ROOT / "scripts" / "case0003_local_continue.ps1").read_text(encoding="utf-8")
    assert "openworker/case0003-local-continue/v10" in text
    assert "streetview-browser-screenshots/v3" in text
    assert "orthophoto-workspace/v2" in text
    assert "function Geo-OK" in text
    assert "$acceptedGeo=Read-Json" in text
    assert "accepted-geo+sha+producer-provenance+semantic-visibility" in text
    assert "r.plan.latitude" in text
    assert "r.plan.longitude" in text


def test_case0003_imagery_submit_uses_same_geo_bound_contract():
    text = (ROOT / "scripts" / "case0003_local_imagery_parallel.ps1").read_text(encoding="utf-8")
    assert "openworker/case0003-local-imagery-parallel/v4" in text
    assert "streetview-browser-screenshots/v3" in text
    assert "orthophoto-workspace/v2" in text
    assert "function Geo-OK" in text
    assert "accepted_geolocation" in text
    assert "r.plan.latitude" in text
    assert "r.plan.longitude" in text
