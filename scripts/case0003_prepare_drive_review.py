"""Prepare Case 0003 for ChatGPT review through Google Drive without auto-accepting it.

Mechanical verification and cloud review are deliberately separate:
- this script re-validates current local physical outputs,
- opens a fresh WorkLedger review revision,
- builds an immutable review bundle,
- copies it into the bounded Google Drive Desktop review sync root,
- leaves the revision unaccepted until a connector-grounded ChatGPT receipt is applied.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coworker.review_cycle import ReviewArtifact, ReviewCycle
from coworker.runtimes.engineering_scope import EngineeringScope
from coworker.runtimes.job_binding import JobBindingStore
from coworker.work_ledger import WorkLedger

PROJECT_ID = "prj_ba726e251d380d72507e2172d4946d78"
PROJECT_CODE = "OW-2786FE219ABF"
JOB_ID = "job_9d9ee94e021ed007f3aa13c67a40acc5"
JOB_CODE = "OWJ-20260816030152-03D90D"
ASSIGNED_HOST = "DESKTOP-UL7V2VV"
DTM_CATALOG = Path(r"D:\TaiwanDTM\catalog\dtm_catalog.sqlite")


class ReviewPrepareError(RuntimeError):
    pass


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ReviewPrepareError(f"{label} missing/empty: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ReviewPrepareError(f"{label} invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewPrepareError(f"{label} must be an object: {path}")
    return value


def _file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise ReviewPrepareError(f"{label} missing/empty: {path}")
    return path


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _png_size(path: Path) -> tuple[int, int]:
    _file(path, "PNG")
    with path.open("rb") as fh:
        header = fh.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ReviewPrepareError(f"not canonical PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _within(root: Path, path: Path) -> Path:
    root = root.resolve(); path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ReviewPrepareError(f"workspace escape: {path}") from exc
    return path


def _ensure_binding(workspace: Path):
    host = JobBindingStore.current_host()
    if host.casefold() != ASSIGNED_HOST.casefold():
        raise ReviewPrepareError(f"assigned host mismatch: expected={ASSIGNED_HOST} actual={host}")
    store = JobBindingStore(workspace)
    binding = store.load()
    if binding is None:
        binding = store.create(EngineeringScope(PROJECT_ID, PROJECT_CODE, JOB_ID, JOB_CODE))
    if binding.project_id != PROJECT_ID or binding.job_id != JOB_ID or binding.job_code != JOB_CODE:
        raise ReviewPrepareError("existing JobBinding does not match Case 0003 authority")
    return binding


def _open_review_revision(ledger: WorkLedger, work: dict[str, Any]) -> dict[str, Any]:
    head_id = str(work.get("head_revision_id") or "")
    if not head_id:
        raise ReviewPrepareError("WorkLedger has no HEAD")
    head = ledger.get_revision(head_id)
    if head.get("status") == "rework_required":
        rev = ledger.open_rework(
            head_id,
            goal="Case 0003 local-first mechanical verification before Drive review",
            plan={"case_id":"0003","gate":"DRIVE_REVIEW_PREPARE","assigned_host":ASSIGNED_HOST,"transport":"openworker-local-first"},
            reason=head.get("reason", ""),
            gap_owner_repo=head.get("gap_owner_repo", ""),
        )
    else:
        rev = ledger.open_revision(
            work["work_id"],
            kind="review",
            goal="Case 0003 local-first mechanical verification before Drive review",
            parent_revision_id=head_id,
            plan={"case_id":"0003","gate":"DRIVE_REVIEW_PREPARE","assigned_host":ASSIGNED_HOST,"transport":"openworker-local-first"},
        )
    ledger.set_revision_status(rev["revision_id"], "verifying", reason="mechanical verification before Drive review")
    return rev


def _record(ledger: WorkLedger, revision_id: str, logical_name: str, path: Path, capability_id: str) -> None:
    ledger.add_file_artifact(
        revision_id,
        logical_name=logical_name,
        path=path,
        provenance={"case_id":"0003","capability_id":capability_id,"transport":"openworker-local-first"},
        verification_status="passed",
    )


def _mechanical_checks(workspace: Path, ledger: WorkLedger, revision_id: str) -> tuple[dict[str, Any], list[ReviewArtifact]]:
    checks: dict[str, Any] = {}

    if not DTM_CATALOG.is_file() or DTM_CATALOG.stat().st_size <= 0:
        raise ReviewPrepareError(f"DTM catalog unavailable: {DTM_CATALOG}")
    conn = sqlite3.connect(f"file:{DTM_CATALOG.as_posix()}?mode=ro", uri=True)
    try:
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        tables = int(conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
    finally:
        conn.close()
    if quick.lower() != "ok" or tables <= 0:
        raise ReviewPrepareError(f"DTM catalog rejected quick_check={quick} tables={tables}")
    checks["dtm"] = {"status":"passed","quick_check":quick,"table_count":tables}

    terrain = workspace / "terrain"
    ctx = _load_json(_within(workspace, terrain / "terrain-context.json"), "terrain context")
    _file(_within(workspace, terrain / "terrain-grid.json"), "terrain grid")
    _file(_within(workspace, terrain / "terrain.obj"), "terrain mesh")
    if ctx.get("schema_version") != "terrain-context/v1" or int(ctx.get("usable_tiles", 0)) <= 0:
        raise ReviewPrepareError("terrain context rejected")
    checks["terrain"] = {"status":"passed","usable_tiles":int(ctx["usable_tiles"])}
    _record(ledger, revision_id, "terrain-context.json", terrain / "terrain-context.json", "terrain.aoi.build")
    _record(ledger, revision_id, "terrain.obj", terrain / "terrain.obj", "terrain.aoi.build")

    consumer = _load_json(_within(workspace, workspace / "consumer" / "consumer-orchestration.json"), "consumer orchestration")
    if consumer.get("schema_version") != "consumer-orchestration/v1":
        raise ReviewPrepareError("consumer orchestration schema mismatch")
    checks["consumer"] = {"status":"passed"}
    _record(ledger, revision_id, "consumer-orchestration.json", workspace / "consumer" / "consumer-orchestration.json", "terrain.consumer.orchestrate")

    blender = workspace / "blender"
    blend = _file(_within(workspace, blender / "terrain-scene.blend"), "Blender scene")
    render = _file(_within(workspace, blender / "terrain-render.png"), "Blender render")
    bw, bh = _png_size(render)
    bev = _load_json(blender / "blender-scene-evidence.json", "Blender evidence")
    if bev.get("schema_version") != "blender-scene-evidence/v1":
        raise ReviewPrepareError("Blender evidence schema mismatch")
    checks["blender"] = {"status":"passed","render":[bw,bh],"scene_sha256":_sha256(blend),"render_sha256":_sha256(render)}
    _record(ledger, revision_id, "terrain-scene.blend", blend, "terrain.blender.execute")
    _record(ledger, revision_id, "terrain-render.png", render, "terrain.blender.execute")

    scenex = workspace / "scenex"
    shot = _file(_within(workspace, scenex / "terrain-browse.png"), "SceneX screenshot")
    sxev = _load_json(scenex / "terrain-browse-evidence.json", "SceneX evidence")
    sxm = _load_json(scenex / "scenex-workspace.json", "SceneX workspace")
    sw, sh = _png_size(shot)
    if sxm.get("schema_version") != "scenex-workspace-browse/v1" or sxm.get("ok") is not True:
        raise ReviewPrepareError("SceneX workspace rejected")
    if int(sxm.get("active_chunks", 0)) <= 0 or int(sxm.get("terrain_geometry_count", 0)) <= 0:
        raise ReviewPrepareError("SceneX terrain diagnostics rejected")
    if (sw, sh) != (1280, 720):
        raise ReviewPrepareError(f"SceneX screenshot size rejected: {(sw, sh)}")
    checks["scenex"] = {"status":"passed","viewport":[sw,sh],"active_chunks":int(sxm["active_chunks"]),"terrain_geometry_count":int(sxm["terrain_geometry_count"]),"screenshot_sha256":_sha256(shot)}
    _record(ledger, revision_id, "scenex-terrain-browse.png", shot, "scenex.terrain.real_browse")
    _record(ledger, revision_id, "scenex-terrain-browse-evidence.json", scenex / "terrain-browse-evidence.json", "scenex.terrain.real_browse")

    os_receipt = _load_json(workspace / "evidence" / "case0003-os-delivery-receipt.json", "OS delivery receipt")
    if os_receipt.get("ok") is not True:
        raise ReviewPrepareError("OS delivery receipt rejected")
    delivery = os_receipt.get("delivery") or {}
    if not isinstance(delivery, dict) or str(delivery.get("status") or "") != "published":
        raise ReviewPrepareError("OS delivery is not published")
    manifest = _file(Path(str(delivery.get("manifest_path") or "")), "OS delivery manifest")
    website = _file(Path(str(delivery.get("website_entry") or "")), "OS delivery website")
    delivery_root = _file(manifest, "OS delivery manifest").parent
    checksum_manifest = _file(delivery_root / "checksum-manifest.json", "OS checksum manifest")
    checks["os_delivery"] = {"status":"passed","delivery_id":delivery.get("id"),"revision":delivery.get("revision"),"manifest_sha256":_sha256(manifest),"website_sha256":_sha256(website)}
    _record(ledger, revision_id, "delivery-manifest.json", manifest, "engineering_os.delivery.publish")
    _record(ledger, revision_id, "delivery-index.html", website, "engineering_os.delivery.publish")

    acceptance_dir = workspace / "acceptance" / "openworker-final"
    acceptance_dir.mkdir(parents=True, exist_ok=True)
    mechanical = acceptance_dir / f"mechanical-acceptance-{revision_id}.json"
    mechanical.write_text(json.dumps({"schema_version":"openworker-case0003-mechanical-acceptance/v3","case_id":"0003","revision_id":revision_id,"assigned_host":ASSIGNED_HOST,"transport":"openworker-local-first","checks":checks,"ok":True,"status":"WAITING_DRIVE_REVIEW"}, ensure_ascii=False, indent=2), encoding="utf-8")
    _record(ledger, revision_id, "mechanical-acceptance.json", mechanical, "openworker.case0003.review_prepare")

    artifacts = [
        ReviewArtifact("blender-render", render),
        ReviewArtifact("scenex-browse", shot),
        ReviewArtifact("scenex-evidence", scenex / "terrain-browse-evidence.json"),
        ReviewArtifact("delivery-index", website),
        ReviewArtifact("delivery-manifest", manifest),
        ReviewArtifact("checksum-manifest", checksum_manifest),
        ReviewArtifact("mechanical-acceptance", mechanical),
    ]
    return checks, artifacts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    p.add_argument("--drive-sync-root", default=os.environ.get("OPENWORKER_REVIEW_DRIVE_ROOT", ""))
    args = p.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ReviewPrepareError(f"workspace unavailable: {workspace}")
    binding = _ensure_binding(workspace)
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work = ledger.get_work_by_code(binding.job_code)
        revision = _open_review_revision(ledger, work)
        revision_id = str(revision["revision_id"])
        checks, artifacts = _mechanical_checks(workspace, ledger, revision_id)
        for name, evidence in checks.items():
            ledger.set_check(revision_id, name=f"Mechanical:{name}", status="passed", required=True, evidence=evidence)
        cycle = ReviewCycle(workspace)
        bundle = cycle.build_bundle(
            ledger,
            revision_id,
            artifacts=artifacts,
            review_dimensions=[
                "engineering semantic correctness",
                "terrain/bridge visual plausibility",
                "camera framing and readability",
                "SceneX terrain presentation quality",
                "delivery completeness and usefulness",
                "parameter-tuning opportunities",
                "tool capability gaps that cannot be fixed by parameters",
            ],
            current_parameters={},
            allowed_parameter_keys=[],
            capability_id="openworker.case0003.final_review",
            owning_repo="liuxb99/openworker",
        )
        drive_target = cycle.handoff_to_drive_sync(bundle, drive_sync_root=args.drive_sync_root or None, work_code=JOB_CODE)
        manifest = _load_json(bundle / "manifest.json", "review bundle manifest")
        request = _load_json(bundle / "review-request.json", "review request")
        ledger.set_revision_status(revision_id, "blocked", reason="WAITING_DRIVE_REVIEW")
        out = {
            "schema_version":"openworker-case0003-drive-review-prepare/v1",
            "case_id":"0003",
            "revision_id":revision_id,
            "parent_revision_id":revision.get("parent_revision_id") or "",
            "status":"WAITING_DRIVE_REVIEW",
            "ok":False,
            "accepted_revision_id":"",
            "delivered_revision_id":"",
            "bundle_root":str(bundle),
            "drive_sync_target":str(drive_target),
            "bundle_manifest_sha256":_sha256(bundle / "manifest.json"),
            "review_request_sha256":_sha256(bundle / "review-request.json"),
            "artifact_count":len(manifest.get("files") or []),
            "drive_folder_id":request.get("drive_folder_id"),
            "transport":"google-drive-review-handoff",
            "ledger":ledger.snapshot(work["work_id"]),
        }
        out_path = workspace / "acceptance" / "openworker-final" / f"drive-review-prepare-{revision_id}.json"
        latest = workspace / "acceptance" / "openworker-final" / "drive-review-prepare.json"
        payload = json.dumps(out, ensure_ascii=False, indent=2, default=str)
        out_path.write_text(payload, encoding="utf-8"); latest.write_text(payload, encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0003_DRIVE_REVIEW_PREPARE_FAIL {exc}", file=sys.stderr)
        raise
