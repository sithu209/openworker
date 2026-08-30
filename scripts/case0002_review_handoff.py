"""Case 0002 Aladdin immutable artifact review -> Google Drive handoff.

This wrapper intentionally owns only review governance. Comfyx-Studio remains
story/director/workspace authority, ComfyX remains image/video generation
authority, and OpenMAIC remains presentation authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from coworker.review_cycle import ReviewArtifact, ReviewCycle, ReviewCycleError
from coworker.work_ledger import WorkLedger, WorkLedgerError

WORK_CODE = "CASE-0002-ALADDIN"
WORK_TITLE = "Case 0002 Aladdin cross-tool production review"
ASSIGNED_HOST = "DESKTOP-ODAQN0D"


def _nonempty(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ReviewCycleError(f"required review artifact missing/empty: {path}")
    return path


def _collect_artifacts(workspace: Path, phase: str) -> list[ReviewArtifact]:
    artifacts: list[ReviewArtifact] = []

    required = [
        ("storyboard-request-bound", workspace / "presentation" / "storyboard-request.bound.json"),
        ("storyboard-pptx", workspace / "presentation" / "storyboard.pptx"),
        ("storyboard-manifest", workspace / "presentation" / "storyboard.manifest.json"),
    ]
    for logical, path in required:
        artifacts.append(ReviewArtifact(logical, _nonempty(path)))

    image_paths = sorted(
        p for p in (workspace / "visual-assets").rglob("*")
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"} and p.stat().st_size > 0
    )
    if not image_paths:
        raise ReviewCycleError("Case 0002 review requires at least one physical storyboard/reference image")
    for index, path in enumerate(image_paths, start=1):
        artifacts.append(ReviewArtifact(f"visual-{index:03d}-{path.stem}", path))

    evidence_dir = workspace / "evidence"
    for path in sorted(evidence_dir.glob("*.json")) if evidence_dir.is_dir() else []:
        if path.stat().st_size > 0:
            artifacts.append(ReviewArtifact(f"evidence-{path.stem}", path))

    if phase == "final":
        video_paths = sorted(
            p for p in workspace.rglob("*.mp4")
            if p.is_file() and p.stat().st_size > 0 and ".openworker" not in p.parts
        )
        if not video_paths:
            raise ReviewCycleError("final Case 0002 review requires at least one physical MP4")
        for index, path in enumerate(video_paths, start=1):
            artifacts.append(ReviewArtifact(f"video-{index:03d}-{path.stem}", path))

    return artifacts


def _prepare_revision(ledger: WorkLedger, workspace: Path, phase: str) -> tuple[dict[str, Any], str]:
    try:
        work = ledger.get_work_by_code(WORK_CODE)
    except WorkLedgerError:
        work = ledger.create_work(
            code=WORK_CODE,
            title=WORK_TITLE,
            workspace=str(workspace),
            goal="ChatGPT visual/semantic review of physical Case 0002 artifacts",
            plan={"case_id": "0002", "phase": phase, "assigned_host": ASSIGNED_HOST},
        )

    head_id = str(work.get("head_revision_id") or "")
    if not head_id:
        raise ReviewCycleError("Case 0002 WorkLedger has no HEAD")
    head = ledger.get_revision(head_id)
    if head["status"] == "open" and int(head["revision_no"]) == 1:
        revision_id = head_id
    elif head["status"] == "rework_required":
        revision_id = ledger.open_rework(
            head_id,
            goal=f"Case 0002 {phase} review after rework",
            plan={"case_id": "0002", "phase": phase, "github_run_id": os.environ.get("GITHUB_RUN_ID", "")},
            reason=head.get("reason", ""),
            gap_owner_repo=head.get("gap_owner_repo", ""),
        )["revision_id"]
    else:
        revision_id = ledger.open_revision(
            work["work_id"],
            kind="acceptance",
            goal=f"Case 0002 {phase} immutable artifact review",
            parent_revision_id=head_id,
            plan={"case_id": "0002", "phase": phase, "github_run_id": os.environ.get("GITHUB_RUN_ID", "")},
        )["revision_id"]
    ledger.set_revision_status(revision_id, "verifying", reason="preparing immutable ChatGPT review bundle")
    return ledger.get_work_by_code(WORK_CODE), str(revision_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--phase", choices=["storyboard", "final"], default="storyboard")
    parser.add_argument("--drive-sync-root", default=os.environ.get("OPENWORKER_REVIEW_DRIVE_ROOT", ""))
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ReviewCycleError(f"workspace unavailable: {workspace}")
    host = os.environ.get("COMPUTERNAME", "").strip()
    if host and host.casefold() != ASSIGNED_HOST.casefold():
        raise ReviewCycleError(f"CASE0002_ASSIGNED_HOST_MISMATCH host={host} assigned={ASSIGNED_HOST}")

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        work, revision_id = _prepare_revision(ledger, workspace, args.phase)
        artifacts = _collect_artifacts(workspace, args.phase)
        for artifact in artifacts:
            ledger.add_file_artifact(
                revision_id,
                logical_name=artifact.logical_name,
                path=artifact.path,
                provenance={"case_id": "0002", "phase": args.phase, "review_transport": "google-drive-temp"},
                verification_status="passed",
            )
        ledger.set_check(
            revision_id,
            name="LLM Semantic Review",
            status="pending",
            required=True,
            evidence={"reviewer": "ChatGPT", "phase": args.phase},
            reason="waiting for ChatGPT inspection of physical artifacts",
        )

        allowed = [
            "video.duration_sec",
            "video.width",
            "video.height",
            "video.acceleration_profile",
            "video.seed",
            "presentation.image_scale",
        ]
        cycle = ReviewCycle(workspace)
        bundle = cycle.build_bundle(
            ledger,
            revision_id,
            artifacts=artifacts,
            review_dimensions=[
                "story and storyboard semantic correctness",
                "Aladdin/Genie character consistency",
                "scene and magic-lamp continuity",
                "shot composition and camera readability",
                "storyboard image quality and reuse suitability for video",
                "OpenMAIC slide readability and image placement",
                "video motion/temporal coherence" if args.phase == "final" else "readiness for later video generation",
                "subtitle and delivery quality" if args.phase == "final" else "presentation completeness",
                "parameter-tuning opportunities",
                "tool capability gaps requiring owning-repository repair",
            ],
            current_parameters={},
            allowed_parameter_keys=allowed,
            capability_id=f"openworker.case0002.{args.phase}_review",
            owning_repo="liuxb99/openworker",
        )
        drive_target = cycle.handoff_to_drive_sync(
            bundle,
            drive_sync_root=args.drive_sync_root,
            work_code=WORK_CODE,
        )
        ledger.set_revision_status(revision_id, "blocked", reason="WAITING_LLM_REVIEW: Google Drive review bundle handed off")
        result = {
            "schema_version": "openworker-case0002-review-handoff/v1",
            "case_id": "0002",
            "phase": args.phase,
            "status": "WAITING_LLM_REVIEW",
            "work_code": WORK_CODE,
            "revision_id": revision_id,
            "artifact_count": len(artifacts),
            "review_bundle": str(bundle),
            "drive_handoff_path": str(drive_target),
            "drive_folder_id": cycle.drive_folder_id,
            "accepted_revision_id": "",
            "delivered_revision_id": "",
            "ledger": ledger.snapshot(work["work_id"]),
        }
        out = workspace / "acceptance" / "openworker-review" / f"handoff-{revision_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        latest = out.parent / "handoff-latest.json"
        latest.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0002_REVIEW_HANDOFF_FAIL {exc}", file=os.sys.stderr)
        raise
