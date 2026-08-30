from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import CaseWorklist, CaseWorklistError, CaseWorklistStore, StepStatus

_INTERNAL_EVIDENCE_KEYS = {"__openworker_active_action", "__openworker_active_execution"}


def _load_manifest(path: Path) -> CaseWorklist:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise CaseWorklistError("worklist manifest root must be an object")
    return CaseWorklist.from_dict(raw)


def sync_manifest(workspace_root: str | Path, manifest_path: str | Path) -> CaseWorklist:
    store = CaseWorklistStore(workspace_root)
    manifest = _load_manifest(Path(manifest_path).resolve())
    if Path(manifest.workspace_root).resolve() != Path(workspace_root).resolve():
        raise CaseWorklistError("manifest workspace_root does not match --workspace-root")

    if not store.path.is_file():
        store.save(manifest)
        return manifest

    existing = store.load()
    if existing.case_id != manifest.case_id:
        raise CaseWorklistError("manifest case_id does not match durable worklist")
    if existing.assigned_host != manifest.assigned_host:
        raise CaseWorklistError("manifest assigned_host does not match durable worklist")

    existing_by_id = {step.step_id: step for step in existing.steps}
    merged_steps = []
    for declared in manifest.steps:
        old = existing_by_id.get(declared.step_id)
        if old is not None and old.status in {StepStatus.PASSED, StepStatus.SKIPPED}:
            declared.status = old.status
            declared.evidence = dict(old.evidence)
            declared.blocker = ""
        else:
            declared.status = StepStatus.PENDING
            declared.blocker = ""
            if old is not None:
                declared.evidence = {
                    key: value
                    for key, value in old.evidence.items()
                    if key not in _INTERNAL_EVIDENCE_KEYS
                }
        merged_steps.append(declared)

    # Preserve active repair steps that are not part of the canonical manifest.
    declared_ids = {step.step_id for step in merged_steps}
    for old in existing.steps:
        if old.kind == "repair" and old.step_id not in declared_ids and old.status not in {StepStatus.PASSED, StepStatus.SKIPPED}:
            merged_steps.append(old)

    merged = CaseWorklist(
        case_id=manifest.case_id,
        workspace_root=manifest.workspace_root,
        assigned_host=manifest.assigned_host,
        steps=merged_steps,
        schema_version=manifest.schema_version,
        revision=max(existing.revision, manifest.revision) + 1,
    )
    store.save(merged)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    worklist = sync_manifest(args.workspace_root, args.manifest)
    payload = worklist.as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(
        f"CASE_WORKLIST_SYNCED path={CaseWorklistStore(args.workspace_root).path} "
        f"next={payload['canonical_next_step_id']} revision={payload['revision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
