"""Case 0003 mechanical acceptance -> Google Drive LLM review handoff.

This intentionally does NOT accept/deliver the WorkLedger revision. Mechanical
checks only prove that the physical pipeline can be reopened. Semantic/visual
acceptance is delegated to ReviewCycle and must return as an LLM review receipt.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from coworker.review_bundle_binding import write_manifest_sha256_sidecar
from coworker.review_cycle import ReviewArtifact, ReviewCycle, ReviewCycleError
from coworker.work_ledger import WorkLedger


def _load_case_module():
    path = Path(__file__).with_name("case0003_final_acceptance.py")
    spec = importlib.util.spec_from_file_location("openworker_case0003_final_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Case 0003 verifier: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--drive-sync-root", default=os.environ.get("OPENWORKER_REVIEW_DRIVE_ROOT", ""))
    args = parser.parse_args(argv)

    case = _load_case_module()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise case.AcceptanceFailure(f"workspace unavailable: {workspace}")

    acceptance_dir = workspace / "acceptance" / "openworker-final"
    acceptance_dir.mkdir(parents=True, exist_ok=True)
    binding = case._ensure_binding(workspace)
    case.JobBindingStore(workspace).load()
    ledger, work, revision_id = case._prepare_revision(workspace, binding)
    state_path = acceptance_dir / f"work-ledger-final-acceptance-{revision_id}.json"
    latest_path = acceptance_dir / "work-ledger-final-acceptance.json"

    results: dict[str, Any] = {
        "schema_version": "openworker-case0003-final-acceptance/v2",
        "case_id": "0003",
        "workspace": str(workspace),
        "computer_name": case.JobBindingStore.current_host(),
        "revision_id": revision_id,
        "parent_revision_id": ledger.get_revision(revision_id).get("parent_revision_id"),
        "checks": {},
        "ok": False,
        "status": "VERIFYING_MECHANICAL",
    }

    checks: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("DTM", lambda: case._check_dtm(workspace, ledger, revision_id)),
        ("AOI", lambda: case._check_aoi(workspace, ledger, revision_id)),
        ("Consumer", lambda: case._check_consumer(workspace, ledger, revision_id)),
        ("Blender", lambda: case._check_blender(workspace, ledger, revision_id, acceptance_dir)),
        ("SceneX", lambda: case._check_scenex(workspace, ledger, revision_id)),
        ("OS", lambda: case._check_os(workspace, ledger, revision_id)),
        ("Delivery", lambda: case._check_delivery(workspace, ledger, revision_id)),
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
                    evidence={"fresh_acceptance": True, "historical_run": case.HISTORICAL_RUNS.get(name, ""), **evidence},
                )
                results["checks"][name] = {"status": "passed", **evidence}
                print(f"CASE0003_OPENWORKER_CHECK_PASS {name} {json.dumps(evidence, ensure_ascii=False, sort_keys=True)}")
            except Exception as exc:
                reason = f"{name} Final Acceptance failed: {exc}"
                ledger.set_check(revision_id, name=name, status="failed", required=True, reason=reason)
                ledger.request_rework(
                    revision_id,
                    reason=reason,
                    gap_owner_repo=case.OWNERS[name],
                    verification_plan=[
                        f"repair {case.OWNERS[name]}",
                        f"rerun {name} REAL verification",
                        "rerun OpenWorker Final Acceptance",
                    ],
                )
                results.update(
                    status="REWORK_REQUIRED",
                    gap_owner_repo=case.OWNERS[name],
                    reason=reason,
                    ledger=ledger.snapshot(work["work_id"]),
                )
                results["checks"][name] = {
                    "status": "failed",
                    "reason": reason,
                    "gap_owner_repo": case.OWNERS[name],
                }
                _write_state(state_path, results)
                _write_state(latest_path, results)
                print(f"CASE0003_OPENWORKER_REWORK_REQUIRED check={name} owner={case.OWNERS[name]} reason={reason}")
                return 2

        ledger.set_check(
            revision_id,
            name="LLM Semantic Review",
            status="pending",
            required=True,
            evidence={"review_transport": "google-drive-temp", "reviewer": "ChatGPT"},
            reason="waiting for ChatGPT artifact review",
        )

        cycle = ReviewCycle(workspace)
        review_artifacts = [
            ReviewArtifact("blender-render", workspace / "blender" / "terrain-render.png"),
            ReviewArtifact("scenex-browse", workspace / "scenex" / "terrain-browse.png"),
            ReviewArtifact("scenex-evidence", workspace / "scenex" / "terrain-browse-evidence.json"),
            ReviewArtifact("delivery-index", workspace / case.DELIVERY_REL),
            ReviewArtifact("mechanical-acceptance", state_path),
        ]

        results.update(
            ok=True,
            status="MECHANICAL_PASS_PREPARING_LLM_REVIEW",
            ledger=ledger.snapshot(work["work_id"]),
        )
        _write_state(state_path, results)
        _write_state(latest_path, results)

        bundle = cycle.build_bundle(
            ledger,
            revision_id,
            artifacts=review_artifacts,
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
        manifest_binding = write_manifest_sha256_sidecar(bundle)

        try:
            drive_target = cycle.handoff_to_drive_sync(
                bundle,
                drive_sync_root=args.drive_sync_root,
                work_code=work["code"],
            )
        except ReviewCycleError as exc:
            ledger.set_revision_status(
                revision_id,
                "blocked",
                reason=f"WAITING_DRIVE_HANDOFF: {exc}",
            )
            results.update(
                ok=False,
                status="WAITING_DRIVE_HANDOFF",
                reason=str(exc),
                review_bundle=str(bundle),
                bundle_manifest_sha256=manifest_binding,
                ledger=ledger.snapshot(work["work_id"]),
            )
            _write_state(state_path, results)
            _write_state(latest_path, results)
            print(f"CASE0003_OPENWORKER_WAITING_DRIVE_HANDOFF revision={revision_id} reason={exc}")
            return 3

        ledger.set_revision_status(
            revision_id,
            "blocked",
            reason="WAITING_LLM_REVIEW: Google Drive review bundle handed off",
        )
        results.update(
            ok=True,
            status="WAITING_LLM_REVIEW",
            review_bundle=str(bundle),
            bundle_manifest_sha256=manifest_binding,
            drive_handoff_path=str(drive_target),
            drive_folder_id=cycle.drive_folder_id,
            ledger=ledger.snapshot(work["work_id"]),
        )
        _write_state(state_path, results)
        _write_state(latest_path, results)
        print(
            "CASE0003_OPENWORKER_WAITING_LLM_REVIEW "
            f"revision={revision_id} manifest_sha256={manifest_binding} drive={drive_target}"
        )
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CASE0003_OPENWORKER_REVIEW_HANDOFF_FAIL {exc}", file=sys.stderr)
        raise
