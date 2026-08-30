from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from coworker.review_bundle_binding import write_manifest_sha256_sidecar
from coworker.review_cycle import DEFAULT_DRIVE_FOLDER_ID, ReviewCycleError
from coworker.review_drive import GoogleDriveAPIClient, publish_review_bundle
from scripts.case0004_visual_review_handoff import _collect_artifacts, _safe_name, _sha256, _write_state


def _build_bundle(workspace: Path, run_id: str) -> Path:
    review_id = _safe_name(f"case0004-visual-{run_id}")
    review_parent = workspace / ".openworker" / "reviews"
    review_parent.mkdir(parents=True, exist_ok=True)
    bundle = review_parent / review_id
    if bundle.exists():
        manifest = bundle / "manifest.json"
        request = bundle / "review-request.json"
        if not manifest.is_file() or not request.is_file():
            raise ReviewCycleError(f"existing intermediate review bundle incomplete: {bundle}")
        return bundle

    files = _collect_artifacts(workspace)
    staging = Path(tempfile.mkdtemp(prefix=review_id + "-", dir=str(review_parent)))
    payload_dir = staging / "artifacts"
    payload_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, object]] = []
    total = 0
    try:
        for index, source in enumerate(files, start=1):
            rel = source.relative_to(workspace)
            size = source.stat().st_size
            total += size
            digest = _sha256(source)
            dest_name = f"{index:03d}-{_safe_name(str(rel.with_suffix('')))}{source.suffix.lower()}"
            dest = payload_dir / dest_name
            shutil.copy2(source, dest)
            if _sha256(dest) != digest:
                raise ReviewCycleError(f"review bundle copy SHA mismatch: {source}")
            items.append({
                "logical_name": str(rel).replace("\\", "/"),
                "filename": f"artifacts/{dest_name}",
                "sha256": digest,
                "size_bytes": size,
            })

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
                "identify likely repeated floor/story plan regions",
                "flag geometry/tool gaps before cad.set_story_region",
            ],
            "decision_contract": {
                "do_not_accept_final_delivery": True,
                "next_action": "select/refine Story Region only from reviewed physical evidence",
            },
            "artifacts": items,
        }
        request_path = staging / "review-request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {
            "schema_version": "openworker-review-bundle/v1",
            "review_id": review_id,
            "case_id": "0004",
            "total_bytes": total,
            "files": items,
            "review_request_sha256": _sha256(request_path),
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staging.replace(bundle)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    write_manifest_sha256_sidecar(bundle)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Case 0004 intermediate visual evidence through Google Drive API")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--drive-folder-id", default=os.environ.get("OPENWORKER_REVIEW_DRIVE_FOLDER_ID", DEFAULT_DRIVE_FOLDER_ID))
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ReviewCycleError(f"workspace unavailable: {workspace}")
    bundle = _build_bundle(workspace, str(args.run_id).strip())
    client = GoogleDriveAPIClient.from_environment()
    try:
        receipt = publish_review_bundle(
            bundle,
            work_code="CASE-0004-DWG-VISUAL",
            root_folder_id=str(args.drive_folder_id).strip(),
            uploader=client,
            machine_id=os.environ.get("COMPUTERNAME", "DESKTOP-O87PJNR"),
            metadata={"case_id": "0004", "stage": "story-region-discovery", "run_id": str(args.run_id)},
        )
    finally:
        client.close()

    payload = receipt.to_dict()
    state_path = workspace / "evidence" / f"case0004-visual-drive-api-{args.run_id}.json"
    _write_state(state_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        "CASE0004_VISUAL_DRIVE_API_PASS "
        f"review_id={bundle.name} folder={receipt.drive_revision_folder_id} "
        f"manifest_sha256={receipt.bundle_manifest_sha256} artifacts={len(receipt.files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
