from __future__ import annotations

from types import SimpleNamespace

import pytest

from coworker.work_ledger import WorkLedger, WorkLedgerError
from scripts.case0003_final_acceptance import JOB_CODE, _prepare_revision, _record_artifact


def _seed_work(tmp_path):
    db = tmp_path / ".openworker" / "work-ledger.sqlite"
    ledger = WorkLedger(db)
    work = ledger.create_work(code=JOB_CODE, title="Case 0003 玉井橋", workspace=str(tmp_path))
    head = work["head_revision_id"]
    ledger.close()
    return head


def test_final_acceptance_always_opens_child_revision(tmp_path):
    original = _seed_work(tmp_path)
    binding = SimpleNamespace(job_code=JOB_CODE)

    ledger, work, revision_id = _prepare_revision(tmp_path, binding)
    try:
        revision = ledger.get_revision(revision_id)
        assert revision_id != original
        assert revision["kind"] == "acceptance"
        assert revision["parent_revision_id"] == original
        assert revision["status"] == "verifying"
        assert ledger.get_work(work["work_id"])["head_revision_id"] == revision_id
    finally:
        ledger.close()


def test_final_acceptance_after_failure_opens_rework_child(tmp_path):
    original = _seed_work(tmp_path)
    db = tmp_path / ".openworker" / "work-ledger.sqlite"
    ledger = WorkLedger(db)
    ledger.request_rework(
        original,
        reason="SceneX reopen failed",
        gap_owner_repo="liuxb99/SceneX",
        verification_plan=["rerun SceneX REAL verification"],
    )
    ledger.close()

    binding = SimpleNamespace(job_code=JOB_CODE)
    ledger, _, revision_id = _prepare_revision(tmp_path, binding)
    try:
        revision = ledger.get_revision(revision_id)
        assert revision["kind"] == "rework"
        assert revision["parent_revision_id"] == original
        assert revision["rework_of_revision_id"] == original
        assert revision["gap_owner_repo"] == "liuxb99/SceneX"
        assert revision["status"] == "verifying"
    finally:
        ledger.close()


def test_final_acceptance_duplicate_artifact_is_not_silently_ignored(tmp_path):
    _seed_work(tmp_path)
    binding = SimpleNamespace(job_code=JOB_CODE)
    ledger, _, revision_id = _prepare_revision(tmp_path, binding)
    artifact = tmp_path / "fresh-evidence.json"
    artifact.write_text('{"ok":true}', encoding="utf-8")

    try:
        _record_artifact(ledger, revision_id, "fresh-evidence.json", artifact)
        with pytest.raises(WorkLedgerError, match="already exists in revision"):
            _record_artifact(ledger, revision_id, "fresh-evidence.json", artifact)
    finally:
        ledger.close()
