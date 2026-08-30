from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coworker.work_ledger import WorkLedger

WORK_CODE = "OWJ-20260816030152-03D90D"
HOST = "DESKTOP-UL7V2VV"
TOL = 1e-7


class ImageryAcceptanceError(RuntimeError):
    pass


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ImageryAcceptanceError(f"{label} missing/empty: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ImageryAcceptanceError(f"{label} must be an object")
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def within(workspace: Path, candidate: Path, label: str) -> Path:
    resolved = candidate.expanduser().resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ImageryAcceptanceError(f"{label} escapes canonical workspace: {resolved}") from exc
    return resolved


def same_geo(value: dict[str, Any], lat: float, lng: float) -> bool:
    try:
        return abs(float(value["lat"]) - lat) <= TOL and abs(float(value["lng"]) - lng) <= TOL
    except Exception:
        return False


def require_file_sha(workspace: Path, path_value: Any, expected: Any, label: str) -> tuple[Path, str]:
    path = within(workspace, Path(str(path_value or "")), label)
    if not path.is_file() or path.stat().st_size <= 0:
        raise ImageryAcceptanceError(f"{label} missing/empty: {path}")
    actual = sha256(path)
    want = str(expected or "").strip().lower().removeprefix("sha256:")
    if len(want) != 64 or actual != want:
        raise ImageryAcceptanceError(f"{label} SHA mismatch expected={want} actual={actual}")
    return path, actual


def validate(workspace: Path) -> tuple[dict[str, Any], list[tuple[str, Path, dict[str, Any]]]]:
    geo_path = workspace / "geo" / "geolocation.json"
    geo = load_json(geo_path, "accepted geolocation")
    if geo.get("ok") is not True:
        raise ImageryAcceptanceError("accepted geolocation is not ok")
    loc = geo.get("geolocation") or {}
    lat, lng = float(loc["lat"]), float(loc["lng"])

    sv_path = workspace / "streetview" / "browser" / "streetview-browser-screenshots.json"
    sv = load_json(sv_path, "Street View workspace manifest")
    if sv.get("schema_version") != "streetview-browser-screenshots/v3" or sv.get("ok") is not True or sv.get("transport") != "localexec":
        raise ImageryAcceptanceError("Street View v3/localexec manifest required")
    if str(sv.get("assigned_host") or "").casefold() != HOST.casefold() or not same_geo(sv.get("geolocation") or {}, lat, lng):
        raise ImageryAcceptanceError("Street View host/geolocation mismatch")
    renders = sv.get("renders") or []
    if not isinstance(renders, list) or len(renders) != 4:
        raise ImageryAcceptanceError("Street View requires four renders")

    artifacts: list[tuple[str, Path, dict[str, Any]]] = [
        ("imagery_geo", geo_path, {"stage": "imagery", "role": "accepted-geolocation"}),
        ("streetview_manifest", sv_path, {"stage": "imagery", "schema": sv.get("schema_version")}),
    ]
    seen: set[str] = set()
    sv_shas: dict[str, str] = {}
    for item in renders:
        heading = str(item.get("heading") or "")
        if heading not in {"0", "90", "180", "270"} or heading in seen:
            raise ImageryAcceptanceError(f"invalid/duplicate Street View heading: {heading}")
        seen.add(heading)
        receipt = item.get("receipt") or {}
        if receipt.get("ok") is not True or receipt.get("provider") != "google" or receipt.get("mode") != "headless-render-webgl" or receipt.get("backend") != "angle-swiftshader-webgl":
            raise ImageryAcceptanceError(f"Street View heading {heading} producer provenance rejected")
        if int(receipt.get("width") or 0) != 1920 or int(receipt.get("height") or 0) != 1080 or int(receipt.get("bytes") or 0) <= 0:
            raise ImageryAcceptanceError(f"Street View heading {heading} dimensions/bytes rejected")
        image, digest = require_file_sha(workspace, item.get("path"), receipt.get("sha256"), f"Street View {heading}")
        if receipt.get("output") and within(workspace, Path(str(receipt["output"])), f"Street View {heading} receipt output") != image:
            raise ImageryAcceptanceError(f"Street View heading {heading} output/path mismatch")
        sv_shas[heading] = digest
        artifacts.append((f"streetview_{heading}", image, {"stage": "imagery", "heading": heading, "provider": "google", "mode": receipt.get("mode"), "backend": receipt.get("backend")}))

    ortho_manifest_path = workspace / "orthophoto" / "nlsc-photo2" / "orthophoto-photo2-workspace.json"
    ortho = load_json(ortho_manifest_path, "Orthophoto workspace manifest")
    if ortho.get("schema_version") != "orthophoto-workspace/v2" or ortho.get("ok") is not True or ortho.get("transport") != "localexec":
        raise ImageryAcceptanceError("Orthophoto workspace v2/localexec manifest required")
    if str(ortho.get("assigned_host") or "").casefold() != HOST.casefold() or not same_geo(ortho.get("geolocation") or {}, lat, lng):
        raise ImageryAcceptanceError("Orthophoto host/geolocation mismatch")
    producer = ortho.get("producer_receipt") or {}
    plan = producer.get("plan") or {}
    vis = producer.get("visibility") or {}
    if producer.get("ok") is not True or producer.get("schema_version") != "orthophoto-nlsc-photo2/v1":
        raise ImageryAcceptanceError("Orthophoto producer receipt rejected")
    if plan.get("provider") != "nlsc" or plan.get("layer") != "PHOTO2" or int(plan.get("zoom") or 0) != 19:
        raise ImageryAcceptanceError("Orthophoto PHOTO2/z19 plan required")
    if abs(float(plan.get("latitude")) - lat) > TOL or abs(float(plan.get("longitude")) - lng) > TOL:
        raise ImageryAcceptanceError("Orthophoto producer plan geolocation mismatch")
    if not bool(vis.get("visible")) or float(vis.get("useful_pixel_ratio") or 0) < 0.20 or float(vis.get("luma_stddev") or 0) < 0.02 or float(vis.get("luma_range") or 0) < 0.10:
        raise ImageryAcceptanceError("Orthophoto semantic visibility rejected")
    ortho_image, ortho_sha = require_file_sha(workspace, ortho.get("image"), producer.get("output_sha256"), "Orthophoto PHOTO2 mosaic")
    if producer.get("output_path") and within(workspace, Path(str(producer["output_path"])), "Orthophoto producer output") != ortho_image:
        raise ImageryAcceptanceError("Orthophoto producer output/image mismatch")
    ortho_evidence = within(workspace, Path(str(ortho.get("evidence") or "")), "Orthophoto evidence")
    if not ortho_evidence.is_file() or ortho_evidence.stat().st_size <= 0:
        raise ImageryAcceptanceError("Orthophoto evidence missing/empty")
    artifacts.extend([
        ("orthophoto_workspace_manifest", ortho_manifest_path, {"stage": "imagery", "schema": ortho.get("schema_version")}),
        ("orthophoto_evidence", ortho_evidence, {"stage": "imagery", "provider": "nlsc", "layer": "PHOTO2"}),
        ("orthophoto_photo2", ortho_image, {"stage": "imagery", "provider": "nlsc", "layer": "PHOTO2", "zoom": 19}),
    ])

    identity = {
        "geolocation": {"lat": lat, "lng": lng},
        "geo_sha256": sha256(geo_path),
        "streetview_manifest_sha256": sha256(sv_path),
        "streetview_render_sha256": dict(sorted(sv_shas.items(), key=lambda kv: int(kv[0]))),
        "orthophoto_workspace_sha256": sha256(ortho_manifest_path),
        "orthophoto_evidence_sha256": sha256(ortho_evidence),
        "orthophoto_image_sha256": ortho_sha,
    }
    identity["fingerprint"] = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return identity, artifacts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    args = p.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    identity, artifacts = validate(workspace)
    out_dir = workspace / "acceptance" / "imagery"
    latest = out_dir / "imagery-acceptance.json"
    if latest.is_file():
        old = load_json(latest, "existing imagery acceptance receipt")
        if old.get("schema_version") == "openworker-case0003-imagery-acceptance/v1" and old.get("fingerprint") == identity["fingerprint"]:
            print(json.dumps(old, ensure_ascii=False, sort_keys=True))
            return 0

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(WORK_CODE)
        matching = None
        for rev in reversed(ledger.list_revisions(work["work_id"])):
            plan = rev.get("plan") or {}
            if plan.get("stage") == "imagery" and plan.get("fingerprint") == identity["fingerprint"] and rev.get("status") in {"open", "executing", "verifying", "blocked"}:
                matching = rev
                break
        if matching is None:
            matching = ledger.open_revision(work["work_id"], kind="progress", goal="Case 0003 imagery physical acceptance", plan={"stage": "imagery", "fingerprint": identity["fingerprint"], "accepted_geolocation": identity["geolocation"]})
        rid = matching["revision_id"]
        snap = ledger.snapshot(work["work_id"])
        rev_snap = next(r for r in snap["revisions"] if r["revision_id"] == rid)
        existing_names = {a["logical_name"] for a in rev_snap["artifacts"]}
        for logical, path, provenance in artifacts:
            if logical not in existing_names:
                ledger.add_file_artifact(rid, logical_name=logical, path=path, provenance={**provenance, "case_id": "0003", "fingerprint": identity["fingerprint"]})
        ledger.set_check(rid, name="Imagery Accepted GEO", status="passed", required=True, evidence={"geolocation": identity["geolocation"], "geo_sha256": identity["geo_sha256"]})
        ledger.set_check(rid, name="Street View Physical+Semantic QC", status="passed", required=True, evidence={"manifest_sha256": identity["streetview_manifest_sha256"], "render_sha256": identity["streetview_render_sha256"]})
        ledger.set_check(rid, name="Orthophoto Physical+Semantic QC", status="passed", required=True, evidence={"workspace_sha256": identity["orthophoto_workspace_sha256"], "evidence_sha256": identity["orthophoto_evidence_sha256"], "image_sha256": identity["orthophoto_image_sha256"]})
        ledger.set_revision_status(rid, "verifying", reason="Imagery stage checks passed; whole Case acceptance remains pending downstream OS/Drive/ChatGPT review")
        receipt = {"schema_version": "openworker-case0003-imagery-acceptance/v1", "case_id": "0003", "status": "IMAGERY_ACCEPTED_PENDING_CASE_COMPLETION", "work_code": WORK_CODE, "revision_id": rid, **identity, "accepted_revision_id": "", "delivered_revision_id": ""}
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(receipt, ensure_ascii=False, indent=2, default=str)
        (out_dir / f"imagery-acceptance-{identity['fingerprint']}.json").write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0003_IMAGERY_ACCEPTANCE_FAIL {exc}", file=sys.stderr)
        raise
