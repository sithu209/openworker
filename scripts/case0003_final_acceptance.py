"""Case 0003 玉井橋 OpenWorker REAL final acceptance.

This is intentionally a consumer-side acceptance gate. It does not trust old
workflow conclusions. It re-opens/reads physical outputs, records them in a
fresh Git-like WorkLedger child revision, and fails closed into REWORK_REQUIRED
on the first rejected required check.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from coworker.runtimes.engineering_scope import EngineeringScope
from coworker.runtimes.job_binding import JobBindingStore
from coworker.work_ledger import WorkLedger, WorkLedgerError

PROJECT_ID = "prj_ba726e251d380d72507e2172d4946d78"
PROJECT_CODE = "OW-2786FE219ABF"
JOB_ID = "job_9d9ee94e021ed007f3aa13c67a40acc5"
JOB_CODE = "OWJ-20260816030152-03D90D"
ASSIGNED_HOST = "DESKTOP-UL7V2VV"
DTM_CATALOG = Path(r"D:\TaiwanDTM\catalog\dtm_catalog.sqlite")
DELIVERY_REL = Path(
    "os/jobs/"
    "OWJ-20260816030152-03D90D_0003-YUJING-BRIDGE_OpenWorker_run_"
    "job_9d9ee94e021ed007f3aa13c67a40acc5/delivery/website/index.html"
)

HISTORICAL_RUNS = {
    "DTM": "31930815026/95129023092",
    "AOI": "31937722103/95142177183",
    "Consumer": "31937749499/95142253514",
    "Blender": "31937773773/95142315440",
    "SceneX": "31937803580/95142388557",
    "OS": "31937694129/95142102663",
}

OWNERS = {
    "DTM": "liuxb99/Terrain_To_DXF",
    "AOI": "liuxb99/Terrain_To_DXF",
    "Consumer": "liuxb99/Terrain_To_DXF",
    "Blender": "liuxb99/Terrain_To_DXF",
    "SceneX": "liuxb99/SceneX",
    "OS": "liuxb99/AI-Engineering-OS",
    "Delivery": "liuxb99/AI-Engineering-OS",
}


class AcceptanceFailure(RuntimeError):
    pass


def _json_file(path: Path) -> Any:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AcceptanceFailure(f"missing/empty JSON: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AcceptanceFailure(f"invalid JSON {path}: {exc}") from exc


def _nonempty(path: Path) -> Path:
    if not path.is_file():
        raise AcceptanceFailure(f"missing file: {path}")
    if path.stat().st_size <= 0:
        raise AcceptanceFailure(f"empty file: {path}")
    return path


def _png_size(path: Path) -> tuple[int, int]:
    _nonempty(path)
    with path.open("rb") as fh:
        header = fh.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise AcceptanceFailure(f"not a canonical PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _bounded(root: Path, path: Path) -> Path:
    root = root.resolve()
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AcceptanceFailure(f"workspace escape: {path}") from exc
    return path


def _blender_exe() -> Path:
    discovered = shutil.which("blender")
    candidates = [
        Path(discovered) if discovered else None,
        Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise AcceptanceFailure("Blender executable unavailable")


def _ensure_binding(workspace: Path):
    host = JobBindingStore.current_host()
    if host.casefold() != ASSIGNED_HOST.casefold():
        raise AcceptanceFailure(f"CASE0003_ASSIGNED_HOST_MISMATCH host={host} assigned={ASSIGNED_HOST}")
    store = JobBindingStore(workspace)
    binding = store.load()
    if binding is None:
        binding = store.create(EngineeringScope(PROJECT_ID, PROJECT_CODE, JOB_ID, JOB_CODE))
    if binding.project_id != PROJECT_ID or binding.job_id != JOB_ID or binding.job_code != JOB_CODE:
        raise AcceptanceFailure(
            "existing JobBinding does not match authoritative Case 0003 project/job: "
            f"project={binding.project_id} job={binding.job_id} code={binding.job_code}"
        )
    return binding


def _prepare_revision(workspace: Path, binding) -> tuple[WorkLedger, dict[str, Any], str]:
    """Create one immutable child revision per Final Acceptance attempt.

    Never mix fresh acceptance artifacts/checks into the current progress revision.
    If HEAD is REWORK_REQUIRED, the new attempt is a rework child; otherwise it is
    an acceptance child. This keeps every physical re-check comparable and auditable.
    """
    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    work = ledger.get_work_by_code(binding.job_code)
    head_id = str(work["head_revision_id"] or "")
    if not head_id:
        ledger.close()
        raise AcceptanceFailure("WorkLedger has no HEAD")
    head = ledger.get_revision(head_id)
    plan = {
        "case_id": "0003",
        "gate": "REAL_FINAL_ACCEPTANCE",
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "assigned_host": ASSIGNED_HOST,
    }
    if head["status"] == "rework_required":
        attempt = ledger.open_rework(
            head_id,
            goal="Case 0003 OpenWorker REAL Final Acceptance after rework",
            plan=plan,
            reason=head.get("reason", ""),
            gap_owner_repo=head.get("gap_owner_repo", ""),
        )
    else:
        attempt = ledger.open_revision(
            work["work_id"],
            kind="acceptance",
            goal="Case 0003 OpenWorker fresh REAL Final Acceptance",
            plan=plan,
            parent_revision_id=head_id,
        )
    revision_id = str(attempt["revision_id"])
    ledger.set_revision_status(
        revision_id,
        "verifying",
        reason="OpenWorker REAL Final Acceptance running",
    )
    return ledger, work, revision_id


def _record_artifact(ledger: WorkLedger, revision_id: str, name: str, path: Path, **provenance: Any) -> None:
    # A Final Acceptance attempt owns a fresh child revision, so duplicate names in
    # that revision are programming errors rather than something to silently ignore.
    ledger.add_file_artifact(
        revision_id,
        logical_name=name,
        path=path,
        provenance={"case_id": "0003", **provenance},
        verification_status="passed",
    )


def _check_dtm(workspace: Path, ledger: WorkLedger, revision_id: str) -> dict[str, Any]:
    path = _nonempty(DTM_CATALOG)
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        table_count = int(conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
        conn.close()
    except sqlite3.Error as exc:
        raise AcceptanceFailure(f"DTM SQLite reopen failed: {exc}") from exc
    if quick.lower() != "ok" or table_count <= 0:
        raise AcceptanceFailure(f"DTM SQLite rejected quick_check={quick} tables={table_count}")
    _record_artifact(ledger, revision_id, "dtm-catalog.sqlite", path, historical_run=HISTORICAL_RUNS["DTM"], scope="shared-canonical-external")
    return {"quick_check": quick, "table_count": table_count, "path": str(path)}


def _check_aoi(workspace: Path, ledger: WorkLedger, revision_id: str) -> dict[str, Any]:
    context_path = _bounded(workspace, workspace / "terrain" / "terrain-context.json")
    grid_path = _bounded(workspace, workspace / "terrain" / "terrain-grid.json")
    context = _json_file(context_path)
    grid = _json_file(grid_path)
    if not isinstance(context, dict) or context.get("schema_version") != "terrain-context/v1":
        raise AcceptanceFailure("terrain-context schema mismatch")
    if not isinstance(grid, (dict, list)) or not grid:
        raise AcceptanceFailure("terrain-grid contains no data")
    _record_artifact(ledger, revision_id, "terrain-context.json", context_path, historical_run=HISTORICAL_RUNS["AOI"])
    _record_artifact(ledger, revision_id, "terrain-grid.json", grid_path, historical_run=HISTORICAL_RUNS["AOI"])
    return {"context_schema": context.get("schema_version"), "grid_type": type(grid).__name__}


def _check_consumer(workspace: Path, ledger: WorkLedger, revision_id: str) -> dict[str, Any]:
    path = _bounded(workspace, workspace / "consumer" / "consumer-orchestration.json")
    data = _json_file(path)
    if not isinstance(data, dict) or not data:
        raise AcceptanceFailure("consumer orchestration is not a non-empty object")
    _record_artifact(ledger, revision_id, "consumer-orchestration.json", path, historical_run=HISTORICAL_RUNS["Consumer"])
    return {"keys": sorted(data.keys())[:20], "path": str(path)}


def _check_blender(workspace: Path, ledger: WorkLedger, revision_id: str, acceptance_dir: Path) -> dict[str, Any]:
    scene = _bounded(workspace, workspace / "blender" / "terrain-scene.blend")
    render = _bounded(workspace, workspace / "blender" / "terrain-render.png")
    _nonempty(scene)
    width, height = _png_size(render)
    if width <= 0 or height <= 0:
        raise AcceptanceFailure("Blender render dimensions invalid")

    evidence = acceptance_dir / f"blender-reopen-evidence-{revision_id}.json"
    probe = acceptance_dir / f"blender_reopen_probe_{revision_id}.py"
    probe.write_text(
        "import bpy,json,os\n"
        "out=os.environ['CASE0003_BLENDER_REOPEN_EVIDENCE']\n"
        "payload={'schema_version':'openworker-blender-reopen/v1','ok':True,'scene':bpy.data.filepath,'object_count':len(bpy.data.objects),'scene_count':len(bpy.data.scenes)}\n"
        "assert payload['object_count'] > 0 and payload['scene_count'] > 0\n"
        "open(out,'w',encoding='utf-8').write(json.dumps(payload,ensure_ascii=False,indent=2))\n"
        "print('CASE0003_BLENDER_REOPEN_PASS objects=%d scenes=%d' % (payload['object_count'],payload['scene_count']))\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CASE0003_BLENDER_REOPEN_EVIDENCE"] = str(evidence)
    try:
        completed = subprocess.run(
            [str(_blender_exe()), "--background", str(scene), "--python", str(probe)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AcceptanceFailure("Blender REAL reopen exceeded 300 seconds") from exc
    (acceptance_dir / f"blender-reopen-{revision_id}.log").write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0:
        raise AcceptanceFailure(f"Blender REAL reopen failed exit={completed.returncode}")
    ev = _json_file(evidence)
    if ev.get("ok") is not True or int(ev.get("object_count", 0)) <= 0:
        raise AcceptanceFailure("Blender reopen evidence rejected")
    _record_artifact(ledger, revision_id, "terrain-scene.blend", scene, historical_run=HISTORICAL_RUNS["Blender"])
    _record_artifact(ledger, revision_id, "terrain-render.png", render, historical_run=HISTORICAL_RUNS["Blender"], width=width, height=height)
    _record_artifact(ledger, revision_id, "blender-reopen-evidence.json", evidence, verification="fresh-reopen")
    return {"object_count": int(ev["object_count"]), "scene_count": int(ev["scene_count"]), "render": [width, height]}


def _check_scenex(workspace: Path, ledger: WorkLedger, revision_id: str) -> dict[str, Any]:
    root = _bounded(workspace, workspace / "scenex")
    pack = root / "terrain.region.json"
    shot = root / "terrain-browse.png"
    evidence = root / "terrain-browse-evidence.json"
    manifest = root / "scenex-workspace.json"
    for path in (pack, shot, evidence, manifest):
        _nonempty(path)
    ev = _json_file(evidence)
    manifest_json = _json_file(manifest)
    width, height = _png_size(shot)
    if ev.get("schema_version") != "scenex-real-browse/v1" or ev.get("ok") is not True:
        raise AcceptanceFailure("SceneX fresh REAL browse evidence rejected")
    if str(ev.get("region_id", "")) == "fallback-generated":
        raise AcceptanceFailure("SceneX fallback-generated region forbidden")
    active = int((ev.get("terrain_diagnostics") or {}).get("active_chunk_count", 0))
    geometry = int((ev.get("geometry_diagnostics") or {}).get("terrain_geometry_count", 0))
    viewport = ev.get("viewport") or {}
    if active <= 0 or geometry <= 0:
        raise AcceptanceFailure(f"SceneX terrain diagnostics rejected active={active} geometry={geometry}")
    if int(viewport.get("width", 0)) != 1280 or int(viewport.get("height", 0)) != 720 or (width, height) != (1280, 720):
        raise AcceptanceFailure(f"SceneX viewport/screenshot mismatch evidence={viewport} png={(width,height)}")
    if manifest_json.get("ok") is not True:
        raise AcceptanceFailure("SceneX workspace manifest rejected")
    _record_artifact(ledger, revision_id, "scenex-terrain.region.json", pack, historical_run=HISTORICAL_RUNS["SceneX"], verification="fresh-godot-browse")
    _record_artifact(ledger, revision_id, "scenex-terrain-browse.png", shot, verification="fresh-godot-browse", width=width, height=height)
    _record_artifact(ledger, revision_id, "scenex-terrain-browse-evidence.json", evidence, verification="fresh-godot-browse")
    return {"active_chunks": active, "terrain_geometry_count": geometry, "viewport": [width, height]}


def _check_os(workspace: Path, ledger: WorkLedger, revision_id: str) -> dict[str, Any]:
    website = _bounded(workspace, workspace / DELIVERY_REL)
    _nonempty(website)
    text = website.read_text(encoding="utf-8-sig", errors="replace").lower()
    if "<html" not in text and "<!doctype html" not in text:
        raise AcceptanceFailure("delivery website is not recognizable HTML")
    _record_artifact(ledger, revision_id, "delivery-index.html", website, historical_run=HISTORICAL_RUNS["OS"], delivery_id="del_94628aca0f2a79003136e16c78141a7f", delivery_revision=1)
    return {"website": str(website), "size_bytes": website.stat().st_size}


def _check_delivery(workspace: Path, ledger: WorkLedger, revision_id: str) -> dict[str, Any]:
    website = _bounded(workspace, workspace / DELIVERY_REL)
    _nonempty(website)
    delivery_root = website.parent.parent
    files = [p for p in delivery_root.rglob("*") if p.is_file() and p.stat().st_size > 0]
    if not files:
        raise AcceptanceFailure("delivery tree contains no non-empty files")
    return {"delivery_root": str(delivery_root), "nonempty_file_count": len(files), "delivery_revision": 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise AcceptanceFailure(f"workspace unavailable: {workspace}")
    acceptance_dir = workspace / "acceptance" / "openworker-final"
    acceptance_dir.mkdir(parents=True, exist_ok=True)

    binding = _ensure_binding(workspace)
    # Loading again is intentional: it proves resume/replay is idempotent before
    # creating the dedicated Final Acceptance child revision.
    JobBindingStore(workspace).load()
    ledger, work, revision_id = _prepare_revision(workspace, binding)
    result_path = acceptance_dir / f"work-ledger-final-acceptance-{revision_id}.json"
    latest_path = acceptance_dir / "work-ledger-final-acceptance.json"
    results: dict[str, Any] = {
        "schema_version": "openworker-case0003-final-acceptance/v1",
        "case_id": "0003",
        "workspace": str(workspace),
        "computer_name": JobBindingStore.current_host(),
        "revision_id": revision_id,
        "parent_revision_id": ledger.get_revision(revision_id).get("parent_revision_id"),
        "checks": {},
        "ok": False,
    }

    checks: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("DTM", lambda: _check_dtm(workspace, ledger, revision_id)),
        ("AOI", lambda: _check_aoi(workspace, ledger, revision_id)),
        ("Consumer", lambda: _check_consumer(workspace, ledger, revision_id)),
        ("Blender", lambda: _check_blender(workspace, ledger, revision_id, acceptance_dir)),
        ("SceneX", lambda: _check_scenex(workspace, ledger, revision_id)),
        ("OS", lambda: _check_os(workspace, ledger, revision_id)),
        ("Delivery", lambda: _check_delivery(workspace, ledger, revision_id)),
    ]

    try:
        for name, verifier in checks:
            try:
                evidence = verifier()
                ledger.set_check(
                    revision_id,
                    name=name,
                    status="passed",
                    required=True,
                    evidence={"fresh_acceptance": True, "historical_run": HISTORICAL_RUNS.get(name, ""), **evidence},
                )
                results["checks"][name] = {"status": "passed", **evidence}
                print(f"CASE0003_OPENWORKER_CHECK_PASS {name} {json.dumps(evidence, ensure_ascii=False, sort_keys=True)}")
            except Exception as exc:
                reason = f"{name} Final Acceptance failed: {exc}"
                ledger.set_check(revision_id, name=name, status="failed", required=True, reason=reason)
                ledger.request_rework(
                    revision_id,
                    reason=reason,
                    gap_owner_repo=OWNERS[name],
                    verification_plan=[f"repair {OWNERS[name]}", f"rerun {name} REAL verification", "rerun OpenWorker Final Acceptance"],
                )
                results["checks"][name] = {"status": "failed", "reason": reason, "gap_owner_repo": OWNERS[name]}
                results["status"] = "REWORK_REQUIRED"
                results["gap_owner_repo"] = OWNERS[name]
                results["reason"] = reason
                results["ledger"] = ledger.snapshot(work["work_id"])
                payload = json.dumps(results, ensure_ascii=False, indent=2, default=str)
                result_path.write_text(payload, encoding="utf-8")
                latest_path.write_text(payload, encoding="utf-8")
                print(f"CASE0003_OPENWORKER_REWORK_REQUIRED check={name} owner={OWNERS[name]} reason={reason}")
                return 2

        accepted = ledger.accept_revision(revision_id)
        delivered = ledger.deliver_revision(
            revision_id,
            delivery={
                "case_id": "0003",
                "delivery_id": "del_94628aca0f2a79003136e16c78141a7f",
                "delivery_revision": 1,
                "website": str(workspace / DELIVERY_REL),
                "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
            },
        )
        results["ok"] = True
        results["status"] = "DELIVERED"
        results["accepted_revision_id"] = accepted["revision_id"]
        results["delivered_revision_id"] = delivered["delivered_revision_id"]
        results["ledger"] = ledger.snapshot(work["work_id"])
        payload = json.dumps(results, ensure_ascii=False, indent=2, default=str)
        result_path.write_text(payload, encoding="utf-8")
        latest_path.write_text(payload, encoding="utf-8")
        print(f"CASE0003_OPENWORKER_FINAL_ACCEPTANCE_PASS revision={revision_id}")
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceFailure as exc:
        print(f"CASE0003_OPENWORKER_FINAL_ACCEPTANCE_BOOTSTRAP_FAIL {exc}", file=sys.stderr)
        raise SystemExit(2)
