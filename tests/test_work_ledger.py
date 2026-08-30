from __future__ import annotations

import hashlib

import pytest

from coworker.work_ledger import WorkLedger, WorkLedgerError


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_work_revision_rework_accept_delivery_roundtrip(tmp_path):
    db = tmp_path / "ledger.sqlite"
    ledger = WorkLedger(db)
    work = ledger.create_work(code="CASE-0003", title="玉井橋", workspace=str(tmp_path), goal="REAL close loop")
    work_id = work["work_id"]
    r1 = work["head_revision_id"]

    ledger.add_artifact(r1, logical_name="terrain", path="D:/job/terrain.obj", sha256=_sha("terrain-r1"), size_bytes=100, verification_status="passed")
    ledger.set_check(r1, name="DTM", status="passed")
    ledger.set_check(r1, name="SceneX", status="failed", reason="viewport timeout")

    with pytest.raises(WorkLedgerError, match="not all passed"):
        ledger.accept_revision(r1)

    ledger.request_rework(r1, reason="SceneX timeout", gap_owner_repo="liuxb99/SceneX", verification_plan=["rerun SceneX"])
    assert ledger.get_revision(r1)["status"] == "rework_required"

    r2 = ledger.open_rework(r1, goal="repair SceneX")["revision_id"]
    assert ledger.get_revision(r2)["parent_revision_id"] == r1
    assert ledger.get_revision(r2)["rework_of_revision_id"] == r1

    ledger.add_artifact(r2, logical_name="terrain", path="D:/job/terrain.obj", sha256=_sha("terrain-r2"), size_bytes=120, verification_status="passed")
    ledger.set_check(r2, name="DTM", status="passed")
    ledger.set_check(r2, name="SceneX", status="passed")
    ledger.accept_revision(r2)
    delivered = ledger.deliver_revision(r2, delivery={"delivery_revision": 1})
    assert delivered["accepted_revision_id"] == r2
    assert delivered["delivered_revision_id"] == r2
    ledger.close()

    reopened = WorkLedger(db)
    snap = reopened.snapshot(work_id)
    assert [r["revision_id"] for r in snap["revisions"]] == [r1, r2]
    assert snap["revisions"][0]["artifacts"][0]["sha256"] == _sha("terrain-r1")
    assert snap["revisions"][1]["artifacts"][0]["sha256"] == _sha("terrain-r2")
    assert snap["work"]["accepted_revision_id"] == r2
    assert snap["work"]["delivered_revision_id"] == r2
    reopened.close()


def test_accepted_revision_is_append_only(tmp_path):
    ledger = WorkLedger(tmp_path / "ledger.sqlite")
    work = ledger.create_work(code="W-1", title="one")
    revision = work["head_revision_id"]
    ledger.set_check(revision, name="final", status="passed")
    ledger.accept_revision(revision)

    with pytest.raises(WorkLedgerError, match="immutable"):
        ledger.add_artifact(revision, logical_name="changed", path="x", sha256=_sha("x"), size_bytes=1)
    with pytest.raises(WorkLedgerError, match="immutable"):
        ledger.set_check(revision, name="final", status="failed")
    ledger.close()


def test_required_check_gate_is_fail_closed(tmp_path):
    ledger = WorkLedger(tmp_path / "ledger.sqlite")
    work = ledger.create_work(code="W-2", title="two")
    revision = work["head_revision_id"]

    with pytest.raises(WorkLedgerError, match="at least one required check"):
        ledger.accept_revision(revision)

    ledger.set_check(revision, name="optional", status="failed", required=False)
    with pytest.raises(WorkLedgerError, match="at least one required check"):
        ledger.accept_revision(revision)

    ledger.set_check(revision, name="required", status="skipped", required=True)
    with pytest.raises(WorkLedgerError, match="required=skipped"):
        ledger.accept_revision(revision)
    ledger.close()


def test_delivery_rejects_unaccepted_revision(tmp_path):
    ledger = WorkLedger(tmp_path / "ledger.sqlite")
    work = ledger.create_work(code="W-3", title="three")
    with pytest.raises(WorkLedgerError, match="accepted revision"):
        ledger.deliver_revision(work["head_revision_id"])
    ledger.close()


def test_rollback_moves_head_without_deleting_history(tmp_path):
    ledger = WorkLedger(tmp_path / "ledger.sqlite")
    work = ledger.create_work(code="W-4", title="four")
    work_id = work["work_id"]
    r1 = work["head_revision_id"]
    ledger.set_check(r1, name="final", status="passed")
    ledger.accept_revision(r1)

    r2 = ledger.open_revision(work_id, kind="progress", goal="experiment")["revision_id"]
    assert ledger.get_work(work_id)["head_revision_id"] == r2

    rolled = ledger.move_head_to_accepted(work_id)
    assert rolled["head_revision_id"] == r1
    assert [r["revision_id"] for r in ledger.list_revisions(work_id)] == [r1, r2]
    ledger.close()


def test_duplicate_artifact_in_same_revision_requires_new_revision(tmp_path):
    ledger = WorkLedger(tmp_path / "ledger.sqlite")
    work = ledger.create_work(code="W-5", title="five")
    revision = work["head_revision_id"]
    ledger.add_artifact(revision, logical_name="render", path="a.png", sha256=_sha("a"), size_bytes=10)

    with pytest.raises(WorkLedgerError, match="create a new revision"):
        ledger.add_artifact(revision, logical_name="render", path="b.png", sha256=_sha("b"), size_bytes=11)
    ledger.close()


def test_rework_must_be_explicit(tmp_path):
    ledger = WorkLedger(tmp_path / "ledger.sqlite")
    work = ledger.create_work(code="W-6", title="six")
    revision = work["head_revision_id"]

    with pytest.raises(WorkLedgerError, match="REWORK_REQUIRED"):
        ledger.open_rework(revision, goal="should fail")

    ledger.request_rework(revision, reason="verification failed")
    child = ledger.open_rework(revision, goal="repair")
    assert child["kind"] == "rework"
    assert child["revision_no"] == 2
    ledger.close()
