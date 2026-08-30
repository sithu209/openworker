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
REQUIRED = (
    "terrain-context.json",
    "terrain-build.json",
    "terrain-grid.json",
    "terrain.dxf",
    "terrain-heightmap.raw",
    "terrain-heightmap.json",
    "terrain.obj",
    "terrain-mesh.json",
    "terrain-scene.json",
    "scenex-terrain-scene.json",
)


class TerrainAcceptanceError(RuntimeError):
    pass


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise TerrainAcceptanceError(f"{label} missing/empty: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TerrainAcceptanceError(f"{label} must be an object")
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def within(path: Path, workspace: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise TerrainAcceptanceError(f"artifact escapes canonical workspace: {resolved}") from exc
    return resolved


def same_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def validate(workspace: Path, catalog: Path) -> tuple[dict[str, Any], list[tuple[str, Path, dict[str, Any]]]]:
    workspace = workspace.resolve()
    terrain = workspace / "terrain"
    manifest_path = terrain / "terrain-aoi-workspace.json"
    manifest = load_json(manifest_path, "Terrain AOI workspace manifest")
    if manifest.get("schema_version") != "terrain-aoi-workspace/v2" or manifest.get("ok") is not True:
        raise TerrainAcceptanceError("Terrain AOI workspace v2 required")
    if str(manifest.get("assigned_host") or "").casefold() != HOST.casefold():
        raise TerrainAcceptanceError("Terrain assigned host mismatch")
    if Path(str(manifest.get("workspace_root") or "")).resolve() != workspace:
        raise TerrainAcceptanceError("Terrain workspace identity mismatch")

    geo_path = workspace / "geo" / "geolocation.json"
    geo = load_json(geo_path, "accepted geolocation")
    if geo.get("ok") is not True:
        raise TerrainAcceptanceError("accepted geolocation is not ok")
    lat = float(geo["geolocation"]["lat"])
    lng = float(geo["geolocation"]["lng"])
    mg = manifest.get("geolocation") or {}
    if abs(float(mg.get("lat")) - lat) > TOL or abs(float(mg.get("lng")) - lng) > TOL:
        raise TerrainAcceptanceError("Terrain geolocation mismatch")
    if not same_path(Path(str(mg.get("source_path") or "")), geo_path):
        raise TerrainAcceptanceError("Terrain geolocation source path mismatch")
    geo_sha = sha256(geo_path)
    if str(mg.get("sha256") or "").lower() != geo_sha:
        raise TerrainAcceptanceError("Terrain geolocation SHA mismatch")

    catalog = catalog.expanduser().resolve()
    if not catalog.is_file() or catalog.stat().st_size <= 0:
        raise TerrainAcceptanceError(f"catalog missing/empty: {catalog}")
    mc = manifest.get("catalog") or {}
    if not same_path(Path(str(mc.get("path") or "")), catalog):
        raise TerrainAcceptanceError("Terrain catalog path mismatch")
    catalog_sha = sha256(catalog)
    if int(mc.get("size") or 0) != catalog.stat().st_size or str(mc.get("sha256") or "").lower() != catalog_sha:
        raise TerrainAcceptanceError("Terrain catalog identity mismatch")

    request_path = within(Path(str((manifest.get("request") or {}).get("path") or "")), workspace)
    canonical_request = terrain / "terrain-aoi-build-request.json"
    if not same_path(request_path, canonical_request):
        raise TerrainAcceptanceError("Terrain request path mismatch")
    request_sha = sha256(request_path)
    if str((manifest.get("request") or {}).get("sha256") or "").lower() != request_sha:
        raise TerrainAcceptanceError("Terrain request SHA mismatch")
    if int(manifest.get("usable_tiles") or 0) <= 0:
        raise TerrainAcceptanceError("Terrain usable_tiles must be > 0")

    items = manifest.get("artifacts") or []
    if not isinstance(items, list):
        raise TerrainAcceptanceError("Terrain artifacts must be a list")
    artifacts: list[tuple[str, Path, dict[str, Any]]] = [
        ("terrain_geo", geo_path, {"stage": "terrain", "role": "accepted-geolocation"}),
        ("terrain_aoi_manifest", manifest_path, {"stage": "terrain", "schema": "terrain-aoi-workspace/v2"}),
        ("terrain_aoi_request", request_path, {"stage": "terrain", "role": "build-request"}),
    ]
    artifact_shas: dict[str, str] = {}
    for name in REQUIRED:
        matches = [item for item in items if str(item.get("name") or "") == name]
        if len(matches) != 1:
            raise TerrainAcceptanceError(f"Terrain manifest requires exactly one {name}")
        item = matches[0]
        path = within(Path(str(item.get("path") or "")), workspace)
        canonical = terrain / name
        if not same_path(path, canonical):
            raise TerrainAcceptanceError(f"Terrain artifact path mismatch: {name}")
        if not path.is_file() or path.stat().st_size <= 0:
            raise TerrainAcceptanceError(f"Terrain artifact missing/empty: {name}")
        digest = sha256(path)
        if int(item.get("size") or 0) != path.stat().st_size or str(item.get("sha256") or "").lower() != digest:
            raise TerrainAcceptanceError(f"Terrain artifact identity mismatch: {name}")
        artifact_shas[name] = digest
        artifacts.append((f"terrain_{name.replace('.', '_').replace('-', '_')}", path, {"stage": "terrain", "source_name": name}))

    identity = {
        "geolocation": {"lat": lat, "lng": lng},
        "geo_sha256": geo_sha,
        "catalog_path": str(catalog),
        "catalog_size": catalog.stat().st_size,
        "catalog_sha256": catalog_sha,
        "request_sha256": request_sha,
        "manifest_sha256": sha256(manifest_path),
        "usable_tiles": int(manifest["usable_tiles"]),
        "artifact_sha256": artifact_shas,
    }
    identity["fingerprint"] = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return identity, artifacts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    p.add_argument("--catalog", required=True)
    args = p.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    identity, artifacts = validate(workspace, Path(args.catalog))
    out_dir = workspace / "acceptance" / "terrain"
    latest = out_dir / "terrain-acceptance.json"
    if latest.is_file():
        old = load_json(latest, "existing Terrain acceptance receipt")
        if old.get("schema_version") == "openworker-case0003-terrain-acceptance/v1" and old.get("fingerprint") == identity["fingerprint"]:
            print(json.dumps(old, ensure_ascii=False, sort_keys=True))
            return 0

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(WORK_CODE)
        matching = None
        for rev in reversed(ledger.list_revisions(work["work_id"])):
            plan = rev.get("plan") or {}
            if plan.get("stage") == "terrain" and plan.get("fingerprint") == identity["fingerprint"] and rev.get("status") in {"open", "executing", "verifying", "blocked"}:
                matching = rev
                break
        if matching is None:
            matching = ledger.open_revision(
                work["work_id"],
                kind="progress",
                goal="Case 0003 Terrain AOI physical acceptance",
                plan={"stage": "terrain", "fingerprint": identity["fingerprint"], "accepted_geolocation": identity["geolocation"]},
            )
        rid = matching["revision_id"]
        snap = ledger.snapshot(work["work_id"])
        rev_snap = next(r for r in snap["revisions"] if r["revision_id"] == rid)
        existing = {a["logical_name"] for a in rev_snap["artifacts"]}
        for logical, path, provenance in artifacts:
            if logical not in existing:
                ledger.add_file_artifact(rid, logical_name=logical, path=path, provenance={**provenance, "case_id": "0003", "fingerprint": identity["fingerprint"]})
        ledger.set_check(rid, name="Terrain Accepted GEO", status="passed", required=True, evidence={"geolocation": identity["geolocation"], "geo_sha256": identity["geo_sha256"]})
        ledger.set_check(rid, name="Terrain Catalog Identity", status="passed", required=True, evidence={"path": identity["catalog_path"], "size": identity["catalog_size"], "sha256": identity["catalog_sha256"]})
        ledger.set_check(rid, name="Terrain Physical Artifact QC", status="passed", required=True, evidence={"manifest_sha256": identity["manifest_sha256"], "request_sha256": identity["request_sha256"], "usable_tiles": identity["usable_tiles"], "artifact_sha256": identity["artifact_sha256"]})
        ledger.set_revision_status(rid, "verifying", reason="Terrain stage checks passed; whole Case acceptance remains pending downstream OS/Drive/ChatGPT review")
        receipt = {
            "schema_version": "openworker-case0003-terrain-acceptance/v1",
            "case_id": "0003",
            "status": "TERRAIN_ACCEPTED_PENDING_CASE_COMPLETION",
            "work_code": WORK_CODE,
            "revision_id": rid,
            **identity,
            "accepted_revision_id": "",
            "delivered_revision_id": "",
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(receipt, ensure_ascii=False, indent=2, default=str)
        (out_dir / f"terrain-acceptance-{identity['fingerprint']}.json").write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0003_TERRAIN_ACCEPTANCE_FAIL {exc}", file=sys.stderr)
        raise
