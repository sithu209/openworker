from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_case0003_controller_requires_streetview_sha_and_renderer_provenance() -> None:
    text = _read("scripts/case0003_local_continue.ps1")
    assert "openworker/case0003-local-continue/v9" in text
    assert "streetview-browser-screenshots/v2" in text
    assert "angle-swiftshader-webgl" in text
    assert "headless-render-webgl" in text
    assert "SHA-OK $path ([string]$receipt.sha256)" in text
    assert "1920" in text and "1080" in text


def test_case0003_controller_requires_photo2_visibility_and_sha() -> None:
    text = _read("scripts/case0003_local_continue.ps1")
    assert "orthophoto-photo2-workspace.json" in text
    assert "orthophoto-workspace/v1" in text
    assert "orthophoto-nlsc-photo2/v1" in text
    assert "PHOTO2" in text
    assert "visibility.visible" in text
    assert "useful_pixel_ratio" in text
    assert "luma_stddev" in text
    assert "luma_range" in text
    assert "SHA-OK $image ([string]$r.output_sha256)" in text


def test_case0003_imagery_submit_uses_same_strict_contract() -> None:
    text = _read("scripts/case0003_local_imagery_parallel.ps1")
    assert "openworker/case0003-local-imagery-parallel/v3" in text
    assert "angle-swiftshader-webgl" in text
    assert "orthophoto-photo2-workspace.json" in text
    assert "visibility.visible" in text
    assert "SHA-OK $path ([string]$receipt.sha256)" in text
    assert "SHA-OK $image ([string]$r.output_sha256)" in text
