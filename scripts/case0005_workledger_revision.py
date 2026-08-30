from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from coworker.work_ledger import WorkLedger, WorkLedgerError

WORK_CODE = "CASE0005-SNOW-WHITE"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--final-mp4-relpath", default="final/final.mp4")
    parser.add_argument("--evidence", default="evidence/case0005-workledger-revision.json")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace unavailable: {workspace}")
    final_mp4 = (workspace / args.final_mp4_relpath).resolve()
    try:
        final_mp4.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError("final MP4 escapes workspace") from exc
    if not final_mp4.is_file() or final_mp4.stat().st_size <= 0:
        raise RuntimeError(f"final MP4 missing/empty: {final_mp4}")
    final_sha = sha256_file(final_mp4)

    evidence = (workspace / args.evidence).resolve()
    try:
        evidence.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError("evidence path escapes workspace") from exc

    if evidence.is_file() and evidence.stat().st_size > 0:
        prior = json.loads(evidence.read_text(encoding="utf-8-sig"))
        if isinstance(prior, dict) and prior.get("final_mp4_sha256") == final_sha:
            revision_id = str(prior.get("revision_id") or "").strip()
            if revision_id:
                ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
                try:
                    ledger.get_revision(revision_id)
                finally:
                    ledger.close()
                print(json.dumps(prior, ensure_ascii=False, sort_keys=True))
                return 0

    ledger = WorkLedger(workspace / ".openworker" / "work-ledger.sqlite")
    try:
        try:
            work = ledger.get_work_by_code(WORK_CODE)
        except WorkLedgerError:
            work = ledger.create_work(
                code=WORK_CODE,
                title="Case 0005 Snow White",
                workspace=str(workspace),
                goal="Produce, review and deliver the canonical Snow White short film",
                plan={"case_id": "0005", "execution_route": "local_supervisor"},
            )
            revision = ledger.get_revision(str(work["head_revision_id"]))
        else:
            revision = ledger.open_revision(
                str(work["work_id"]),
                kind="progress",
                goal="Register canonical Snow White final MP4 for semantic/visual review",
                plan={"case_id": "0005", "final_mp4": str(final_mp4)},
            )
        work_id = str(work["work_id"])
        revision_id = str(revision["revision_id"])

        artifact = ledger.add_file_artifact(
            revision_id,
            logical_name="final_mp4",
            path=final_mp4,
            provenance={
                "case_id": "0005",
                "execution_route": "local_supervisor",
                "github_action_used_for_business_execution": False,
            },
            verification_status="passed",
        )
        ledger.set_check(
            revision_id,
            name="physical_final_mp4",
            status="passed",
            required=True,
            evidence={"path": str(final_mp4), "sha256": final_sha, "size_bytes": final_mp4.stat().st_size},
        )
        ledger.set_revision_status(revision_id, "verifying")

        manifest = {
            "schema_version": "openworker-case0005-workledger-manifest/v1",
            "case_id": "0005",
            "work_code": WORK_CODE,
            "work_id": work_id,
            "revision_id": revision_id,
            "final_mp4": str(final_mp4),
            "final_mp4_sha256": final_sha,
            "final_mp4_size_bytes": final_mp4.stat().st_size,
            "artifact_id": artifact["artifact_id"],
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
        }
        manifest_path = workspace / ".openworker" / "revisions" / revision_id / "manifest.json"
        atomic_json(manifest_path, manifest)
        manifest_sha = sha256_file(manifest_path)
        output = {
            **manifest,
            "status": "WAITING_REVIEW",
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_sha,
            "artifact_ids": [artifact["artifact_id"]],
            "ledger": str(workspace / ".openworker" / "work-ledger.sqlite"),
        }
        atomic_json(evidence, output)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    raise SystemExit(main())
