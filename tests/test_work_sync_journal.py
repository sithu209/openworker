from __future__ import annotations

import json

import pytest

from coworker.work_sync_journal import WorkSyncJournal, WorkSyncJournalError


def test_append_verify_and_cursor(tmp_path):
    path = tmp_path / "ul7.jsonl"
    journal = WorkSyncJournal(path, source_host="DESKTOP-UL7V2VV")
    first = journal.append(event_type="revision.created", work_code="OWJ-1", revision_id="rev-1", payload={"kind": "initial"})
    second = journal.append(event_type="artifact.added", work_code="OWJ-1", revision_id="rev-1", payload={"sha256": "a" * 64})
    rows = journal.read_all()
    assert [row["source_sequence"] for row in rows] == [1, 2]
    assert second["previous_hash"] == first["event_hash"]
    cursor = journal.cursor()
    assert cursor["source_host"] == "DESKTOP-UL7V2VV"
    assert cursor["source_sequence"] == 2
    assert cursor["event_hash"] == second["event_hash"]


def test_tampered_history_fails_closed(tmp_path):
    path = tmp_path / "oda.jsonl"
    journal = WorkSyncJournal(path, source_host="DESKTOP-ODAQN0D")
    journal.append(event_type="revision.created", payload={"value": 1})
    journal.append(event_type="revision.status", payload={"status": "verifying"})
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["payload"]["value"] = 999
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(WorkSyncJournalError, match="hash mismatch"):
        journal.read_all()


def test_sequence_gap_fails_closed(tmp_path):
    path = tmp_path / "o87.jsonl"
    journal = WorkSyncJournal(path, source_host="DESKTOP-O87")
    row = journal.append(event_type="revision.created", payload={})
    body = dict(row)
    body.pop("event_hash")
    body["source_sequence"] = 3
    body["previous_hash"] = row["event_hash"]
    forged = dict(body)
    forged["event_hash"] = WorkSyncJournal._event_hash(body)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(forged, sort_keys=True) + "\n")
    with pytest.raises(WorkSyncJournalError, match="source_sequence"):
        journal.read_all()
