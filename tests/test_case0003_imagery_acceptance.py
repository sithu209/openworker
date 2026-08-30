from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coworker.work_ledger import WorkLedger
from scripts import case0003_record_imagery_acceptance as imagery


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _fixture(tmp_path: Path) -> Path:
    w = tmp_path / "workspace"
    w.mkdir()
    geo = w / "geo" / "geolocation.json"
    geo.parent.mkdir()
    geo.write_text(json.dumps({"ok": True, "geolocation": {"lat": 23.124, "lng": 120.462}}), encoding="utf-8")

    sv_dir = w / "streetview" / "browser"
    sv_dir.mkdir(parents=True)
    renders = []
    for heading in ("0", "90", "180", "270"):
        p = sv_dir / f"streetview-browser-heading-{heading}.png"
        _write(p, ("png-" + heading).encode())
        renders.append({
            "heading": heading,
            "path": str(p),
            "receipt": {
                "ok": True,
                "provider": "google",
                "mode": "headless-render-webgl",
                "backend": "angle-swiftshader-webgl",
                "width": 1920,
                "height": 1080,
                "bytes": p.stat().st_size,
                "sha256": _sha(p),
                "output": str(p),
            },
        })
    (sv_dir / "streetview-browser-screenshots.json").write_text(json.dumps({
        "schema_version": "streetview-browser-screenshots/v3",
        "ok": True,
        "transport": "localexec",
        "assigned_host": imagery.HOST,
        "geolocation": {"lat": 23.124, "lng": 120.462},
        "renders": renders,
    }), encoding="utf-8")

    ortho_dir = w / "orthophoto" / "nlsc-photo2"
    ortho_dir.mkdir(parents=True)
    jpg = ortho_dir / "orthophoto-photo2-z19.jpg"
    _write(jpg, b"jpeg-mosaic")
    evidence = ortho_dir / "orthophoto-photo2-evidence.json"
    evidence.write_text(json.dumps({"schema_version": "orthophoto-nlsc-photo2/v1", "ok": True}), encoding="utf-8")
    (ortho_dir / "orthophoto-photo2-workspace.json").write_text(json.dumps({
        "schema_version": "orthophoto-workspace/v2",
        "ok": True,
        "transport": "localexec",
        "assigned_host": imagery.HOST,
        "geolocation": {"lat": 23.124, "lng": 120.462},
        "image": str(jpg),
        "evidence": str(evidence),
        "producer_receipt": {
            "ok": True,
            "schema_version": "orthophoto-nlsc-photo2/v1",
            "plan": {"provider": "nlsc", "layer": "PHOTO2", "zoom": 19, "latitude": 23.124, "longitude": 120.462},
            "visibility": {"visible": True, "useful_pixel_ratio": 0.5, "luma_stddev": 0.1, "luma_range": 0.5},
            "output_sha256": _sha(jpg),
        },
    }), encoding="utf-8")

    ledger = WorkLedger(w / ".openworker" / "work-ledger.sqlite")
    ledger.create_work(code=imagery.WORK_CODE, title="Case 0003")
    ledger.close()
    return w


def test_imagery_acceptance_records_progress_without_accepting_whole_case(tmp_path: Path):
    w = _fixture(tmp_path)
    before = WorkLedger(w / ".openworker" / "work-ledger.sqlite")
    try:
        work = before.get_work_by_code(imagery.WORK_CODE)
        n0 = len(before.list_revisions(work["work_id"]))
    finally:
        before.close()

    assert imagery.main(["--workspace", str(w)]) == 0
    receipt = json.loads((w / "acceptance" / "imagery" / "imagery-acceptance.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "IMAGERY_ACCEPTED_PENDING_CASE_COMPLETION"
    assert receipt["accepted_revision_id"] == ""
    assert receipt["delivered_revision_id"] == ""

    ledger = WorkLedger(w / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(imagery.WORK_CODE)
        revs = ledger.list_revisions(work["work_id"])
        assert len(revs) == n0 + 1
        rev = ledger.get_revision(receipt["revision_id"])
        assert rev["kind"] == "progress"
        assert rev["status"] == "verifying"
        assert work["accepted_revision_id"] in (None, "")
        assert work["delivered_revision_id"] in (None, "")
        snap = ledger.snapshot(work["work_id"])
        rs = next(r for r in snap["revisions"] if r["revision_id"] == receipt["revision_id"])
        assert {c["name"]: c["status"] for c in rs["checks"]} == {
            "Imagery Accepted GEO": "passed",
            "Orthophoto Physical+Semantic QC": "passed",
            "Street View Physical+Semantic QC": "passed",
        }
        assert len(rs["artifacts"]) == 9
    finally:
        ledger.close()

    assert imagery.main(["--workspace", str(w)]) == 0
    ledger = WorkLedger(w / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(imagery.WORK_CODE)
        assert len(ledger.list_revisions(work["work_id"])) == n0 + 1
    finally:
        ledger.close()


def test_imagery_acceptance_rejects_stale_geolocation(tmp_path: Path):
    w = _fixture(tmp_path)
    geo = w / "geo" / "geolocation.json"
    geo.write_text(json.dumps({"ok": True, "geolocation": {"lat": 23.5, "lng": 120.5}}), encoding="utf-8")
    try:
        imagery.main(["--workspace", str(w)])
    except imagery.ImageryAcceptanceError as exc:
        assert "geolocation mismatch" in str(exc)
    else:
        raise AssertionError("stale imagery should be rejected after accepted GEO changes")
