"""Case 0004 intermediate DWG visual review -> Google Drive API handoff.

This is intentionally not final acceptance and does not mutate WorkLedger. It
packages current immutable DWG visual-search evidence and publishes it through the
same proven Google Drive API transport used by Case 0003.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from coworker.review_bundle_binding import write_manifest_sha256_sidecar
from coworker.review_cycle import DEFAULT_DRIVE_FOLDER_ID, ReviewCycleError
from coworker.review_drive import GoogleDriveAPIClient, publish_review_bundle

_ALLOWED_SUFFIXES = {".png", ".json"}
_MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value.strip())
    text = text.strip("-.")
    if not text:
        raise ReviewCycleError("review artifact safe name is empty")
    return text[:180]


def _collect_artifacts(workspace: Path) -> list[Path]:
    required_evidence = [
        workspace / "evidence" / "case0004-inspect-render.json",
        workspace / "evidence" / "case0004-candidate-regions.json",
    ]
    for path in required_evidence:
        if not path.is_file() or path.stat().st_size <= 0:
            raise ReviewCycleError(f"required Case 0004 visual evidence missing/empty: {path}")

    visual_root = workspace / "dwg" / "exports" / "default" / "visual-search"
    if not visual_root.is_dir():
        raise ReviewCycleError(f"DWG visual-search root unavailable: {visual_root}")

    items = [
        path.resolve()
        for path in visual_root.rglob("*")
        if path.is_file() and path.suffix.lower() in _ALLOWED_SUFFIXES and path.stat().st_size > 0
    ]
    items.extend(path.resolve() for path in required_evidence)
    unique = {os.path.normcase(str(path)): path for path in items}
    result = sorted(unique.values(), key=lambda path: str(path).casefold())
    if not any(path.suffix.lower() == ".png" for path in result):
        raise ReviewCycleError("Case 0004 visual review has no physical PNG")
    if not any(path.suffix.lower() == ".json" for path in result):
        raise ReviewCycleError("Case 0004 visual review has no metadata/inventory JSON")
    return result


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument(
        "--drive-folder-id",
        default=os.environ.get("OPENWORKER_REVIEW_DRIVE_FOLDER_ID", DEFAULT_DRIVE_FOLDER_ID),
    )
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ReviewCycleError(f"workspace unavailable: {workspace}")
    run_id = str(args.run_id or "local").strip()
    review_id = _safe_name(f"case0004-visual-{run_id}")
    files = _collect_artifacts(workspace)

    review_parent = workspace / ".openworker" / "reviews"
    review_parent.mkdir(parents=True, exist_ok=True)
    bundle = review_parent / review_id
    if bundle.exists():
        raise ReviewCycleError(f"immutable visual review bundle already exists: {bundle}")
    staging = Path(tempfile.mkdtemp(prefix=review_id + "-", dir=str(review_parent)))
    payload_dir = staging / "artifacts"
    payload_dir.mkdir(parents=True, exist_ok=True)

    manifest_items: list[dict[str, Any]] = []
    total_bytes = 0
    try:
        for index, source in enumerate(files, start=1):
            try:
                rel = source.relative_to(workspace)
            except ValueError as exc:
                raise ReviewCycleError(f"review artifact escapes workspace: {source}") from exc
            size = source.stat().st_size
            total_bytes += size
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ReviewCycleError(f"Case 0004 visual review exceeds {_MAX_TOTAL_BYTES} bytes")
            digest = _sha256(source)
            dest_name = f"{index:03d}-{_safe_name(str(rel.with_suffix('')))}{source.suffix.lower()}"
            dest = payload_dir / dest_name
            shutil.copy2(source, dest)
            if _sha256(dest) != digest:
                raise ReviewCycleError(f"review bundle copy SHA mismatch: {source}")
            manifest_items.append(
                {
                    "logical_name": str(rel).replace("\\", "/"),
                    "filename": f"artifacts/{dest_name}",
                    "sha256": digest,
                    "size_bytes": size,
                }
            )

        request = {
            "schema_version": "openworker-case0004-intermediate-visual-review/v1",
            "case_id": "0004",
            "review_id": review_id,
            "workspace": str(workspace),
            "assigned_host": "DESKTOP-O87PJNR",
            "stage": "story-region-discovery",
            "owning_repo": "liuxb99/DWG_todo",
            "review_dimensions": [
                "identify the primary building/modeling drawing region",
                "distinguish plan/story regions from title blocks, details and unrelated sheets",
                "check whether candidate camera bounds crop meaningful geometry",
                "assess linework readability and whether another render scale is needed",
                "identify likely repeated floor/story plan regions",
                "flag geometry/tool gaps before cad.set_story_region",
            ],
            "decision_contract": {
                "do_not_accept_final_delivery": True,
                "next_action": "select/refine Story Region only from reviewed physical evidence",
            },
            "drive_folder_id": str(args.drive_folder_id),
            "artifacts": manifest_items,
        }
        request_path = staging / "review-request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {
            "schema_version": "openworker-review-bundle/v1",
            "review_id": review_id,
            "case_id": "0004",
            "total_bytes": total_bytes,
            "files": manifest_items,
            "review_request_sha256": _sha256(request_path),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.replace(bundle)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    manifest_sha = write_manifest_sha256_sidecar(bundle)
    client = GoogleDriveAPIClient.from_environment()
    try:
        receipt = publish_review_bundle(
            bundle,
            work_code="OpenWorker-Case-0004",
            root_folder_id=str(args.drive_folder_id),
            uploader=client,
            machine_id=os.environ.get("COMPUTERNAME", "DESKTOP-O87PJNR"),
            metadata={
                "case_id": "0004",
                "stage": "story-region-discovery",
                "run_id": run_id,
                "transport_authority": "coworker.review_drive",
            },
        )
    finally:
        client.close()

    state = {
        "schema_version": "openworker-case0004-visual-drive-handoff/v2",
        "case_id": "0004",
        "review_id": review_id,
        "workspace": str(workspace),
        "bundle": str(bundle),
        "bundle_manifest_sha256": manifest_sha,
        "drive_root_folder_id": receipt.drive_root_folder_id,
        "drive_revision_folder_id": receipt.drive_revision_folder_id,
        "drive_revision_web_view_link": receipt.drive_revision_web_view_link,
        "published_file_count": len(receipt.files),
        "artifact_count": len(manifest_items),
        "total_bytes": total_bytes,
        "transport": "google-drive-api",
        "status": "WAITING_LLM_VISUAL_REVIEW",
    }
    state_path = workspace / "evidence" / f"case0004-visual-drive-handoff-{run_id}.json"
    _write_state(state_path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        "CASE0004_VISUAL_REVIEW_DRIVE_PASS "
        f"review_id={review_id} artifacts={len(manifest_items)} manifest_sha256={manifest_sha} "
        f"drive_revision_folder_id={receipt.drive_revision_folder_id}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0004_VISUAL_REVIEW_HANDOFF_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
