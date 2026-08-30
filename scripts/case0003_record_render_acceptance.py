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

class RenderAcceptanceError(RuntimeError):
    pass

def load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RenderAcceptanceError(f"{label} missing/empty: {path}")
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise RenderAcceptanceError(f"{label} must be object")
    return obj

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def bounded(workspace: Path, value: Any, label: str) -> Path:
    p = Path(str(value or "")).expanduser().resolve()
    try:
        p.relative_to(workspace)
    except ValueError as exc:
        raise RenderAcceptanceError(f"{label} escapes workspace: {p}") from exc
    if not p.is_file() or p.stat().st_size <= 0:
        raise RenderAcceptanceError(f"{label} missing/empty: {p}")
    return p

def require_sha(path: Path, expected: Any, label: str) -> str:
    actual = sha(path)
    want = str(expected or "").strip().lower().removeprefix("sha256:")
    if actual != want:
        raise RenderAcceptanceError(f"{label} SHA mismatch expected={want} actual={actual}")
    return actual

def validate(workspace: Path):
    consumer_path = workspace / "consumer" / "consumer-workspace.json"
    consumer = load(consumer_path, "consumer workspace")
    if consumer.get("schema_version") != "consumer-workspace/v2" or consumer.get("ok") is not True:
        raise RenderAcceptanceError("consumer-workspace/v2 required")
    consumer_fp = str(consumer.get("consumer_fingerprint") or "")
    if not consumer_fp:
        raise RenderAcceptanceError("consumer fingerprint missing")

    terrain_acceptance_path = workspace / "acceptance" / "terrain" / "terrain-acceptance.json"
    terrain_acceptance = load(terrain_acceptance_path, "terrain acceptance")
    terrain_fp = str(terrain_acceptance.get("fingerprint") or "")
    if not terrain_fp:
        raise RenderAcceptanceError("terrain fingerprint missing")

    blender_manifest_path = workspace / "blender" / "blender-workspace.json"
    blender = load(blender_manifest_path, "Blender workspace")
    if blender.get("schema_version") != "blender-workspace/v2" or blender.get("ok") is not True:
        raise RenderAcceptanceError("blender-workspace/v2 required")
    if str(blender.get("consumer_fingerprint") or "") != consumer_fp:
        raise RenderAcceptanceError("Blender consumer fingerprint mismatch")
    if str(blender.get("consumer_workspace_sha256") or "") != sha(consumer_path):
        raise RenderAcceptanceError("Blender consumer workspace SHA mismatch")

    artifacts: list[tuple[str, Path, dict[str, Any]]] = []
    for item in blender.get("artifacts") or []:
        name = str(item.get("name") or "")
        p = bounded(workspace, item.get("path"), f"Blender artifact {name}")
        require_sha(p, item.get("sha256"), f"Blender artifact {name}")
        artifacts.append((f"blender_{name.replace('.', '_')}", p, {"stage": "render", "producer": "blender"}))
    if len(artifacts) < 5:
        raise RenderAcceptanceError("Blender workspace must contain at least five artifacts")

    scenex_manifest_path = workspace / "scenex" / "scenex-workspace.json"
    scenex = load(scenex_manifest_path, "SceneX workspace")
    if scenex.get("schema_version") != "scenex-workspace-browse/v2" or scenex.get("ok") is not True:
        raise RenderAcceptanceError("scenex-workspace-browse/v2 required")
    if str(scenex.get("terrain_fingerprint") or "") != terrain_fp:
        raise RenderAcceptanceError("SceneX terrain fingerprint mismatch")
    if int(scenex.get("active_chunks") or 0) <= 0 or int(scenex.get("terrain_geometry_count") or 0) <= 0:
        raise RenderAcceptanceError("SceneX geometry diagnostics rejected")
    for key, logical in [("region_pack", "scenex_region_pack"), ("screenshot", "scenex_screenshot"), ("evidence", "scenex_evidence")]:
        item = scenex.get(key) or {}
        p = bounded(workspace, item.get("path"), logical)
        require_sha(p, item.get("sha256"), logical)
        artifacts.append((logical, p, {"stage": "render", "producer": "scenex"}))

    artifacts.extend([
        ("blender_workspace_manifest", blender_manifest_path, {"stage": "render", "schema": "blender-workspace/v2"}),
        ("scenex_workspace_manifest", scenex_manifest_path, {"stage": "render", "schema": "scenex-workspace-browse/v2"}),
    ])
    identity = {
        "consumer_fingerprint": consumer_fp,
        "terrain_fingerprint": terrain_fp,
        "consumer_workspace_sha256": sha(consumer_path),
        "blender_workspace_sha256": sha(blender_manifest_path),
        "blender_fingerprint": str(blender.get("blender_fingerprint") or ""),
        "scenex_workspace_sha256": sha(scenex_manifest_path),
        "scenex_fingerprint": str(scenex.get("scenex_fingerprint") or ""),
    }
    if not identity["blender_fingerprint"] or not identity["scenex_fingerprint"]:
        raise RenderAcceptanceError("render fingerprints missing")
    fp = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    identity["fingerprint"] = fp
    return identity, artifacts

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    args = ap.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    identity, artifacts = validate(workspace)
    out_dir = workspace / "acceptance" / "render"
    latest = out_dir / "render-acceptance.json"
    if latest.is_file():
        old = load(latest, "existing render acceptance")
        if old.get("schema_version") == "openworker-case0003-render-acceptance/v1" and old.get("fingerprint") == identity["fingerprint"]:
            print(json.dumps(old, ensure_ascii=False, sort_keys=True))
            return 0

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(WORK_CODE)
        matching = None
        for rev in reversed(ledger.list_revisions(work["work_id"])):
            plan = rev.get("plan") or {}
            if plan.get("stage") == "render" and plan.get("fingerprint") == identity["fingerprint"] and rev.get("status") in {"open", "executing", "verifying", "blocked"}:
                matching = rev
                break
        if matching is None:
            matching = ledger.open_revision(work["work_id"], kind="progress", goal="Case 0003 Blender+SceneX physical acceptance", plan={"stage":"render","fingerprint":identity["fingerprint"],"consumer_fingerprint":identity["consumer_fingerprint"],"terrain_fingerprint":identity["terrain_fingerprint"]})
        rid = matching["revision_id"]
        snap = ledger.snapshot(work["work_id"])
        rev_snap = next(r for r in snap["revisions"] if r["revision_id"] == rid)
        existing = {a["logical_name"] for a in rev_snap["artifacts"]}
        for logical, path, prov in artifacts:
            if logical not in existing:
                ledger.add_file_artifact(rid, logical_name=logical, path=path, provenance={**prov, "case_id":"0003", "fingerprint":identity["fingerprint"]})
        ledger.set_check(rid, name="Blender Current Consumer Binding", status="passed", required=True, evidence={"consumer_fingerprint":identity["consumer_fingerprint"],"blender_fingerprint":identity["blender_fingerprint"]})
        ledger.set_check(rid, name="SceneX Current Terrain Binding", status="passed", required=True, evidence={"terrain_fingerprint":identity["terrain_fingerprint"],"scenex_fingerprint":identity["scenex_fingerprint"]})
        ledger.set_check(rid, name="Render Physical SHA QC", status="passed", required=True, evidence={"blender_workspace_sha256":identity["blender_workspace_sha256"],"scenex_workspace_sha256":identity["scenex_workspace_sha256"]})
        ledger.set_revision_status(rid, "verifying", reason="Blender+SceneX stage checks passed; whole Case acceptance remains pending OS/Drive/ChatGPT review")
        receipt = {"schema_version":"openworker-case0003-render-acceptance/v1","case_id":"0003","status":"RENDER_ACCEPTED_PENDING_CASE_COMPLETION","work_code":WORK_CODE,"revision_id":rid,**identity,"accepted_revision_id":"","delivered_revision_id":""}
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(receipt, ensure_ascii=False, indent=2)
        (out_dir / f"render-acceptance-{identity['fingerprint']}.json").write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        ledger.close()

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0003_RENDER_ACCEPTANCE_FAIL {exc}", file=sys.stderr)
        raise
