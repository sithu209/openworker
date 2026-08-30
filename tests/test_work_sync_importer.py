from __future__ import annotations

import json

import pytest

from coworker.work_sync_importer import WorkSyncImportError, WorkSyncImporter
from coworker.work_sync_journal import WorkSyncJournal


def test_importer_advances_cursor_and_replay_is_idempotent(tmp_path):
    journal = WorkSyncJournal(tmp_path / "ul7.jsonl", source_host="DESKTOP-UL7V2VV")
    first = journal.append(event_type="revision.created", work_code="OWJ-1", revision_id="rev-1", payload={"kind": "initial"})
    second = journal.append(event_type="artifact.added", work_code="OWJ-1", revision_id="rev-1", payload={"sha256": "a" * 64})
    importer = WorkSyncImporter(tmp_path / "state")
    applied: list[str] = []

    result = importer.import_journal(journal, apply_event=lambda row: applied.append(str(row["event_hash"])))
    assert result["imported_events"] == 2
    assert applied == [first["event_hash"], second["event_hash"]]
    assert result["cursor"]["source_sequence"] == 2
    assert result["cursor"]["event_hash"] == second["event_hash"]

    replay = importer.import_journal(journal, apply_event=lambda row: applied.append("duplicate"))
    assert replay["imported_events"] == 0
    assert "duplicate" not in applied

    third = journal.append(event_type="revision.status", work_code="OWJ-1", revision_id="rev-1", payload={"status": "verifying"})
    delta = importer.import_journal(journal, apply_event=lambda row: applied.append(str(row["event_hash"])))
    assert delta["imported_events"] == 1
    assert delta["cursor"]["source_sequence"] == 3
    assert applied[-1] == third["event_hash"]


def test_importer_rejects_valid_but_forked_source_history(tmp_path):
    path = tmp_path / "oda.jsonl"
    journal = WorkSyncJournal(path, source_host="DESKTOP-ODAQN0D")
    original = journal.append(event_type="revision.created", payload={"value": 1})
    importer = WorkSyncImporter(tmp_path / "state")
    importer.import_journal(journal)

    body = {
        "schema": WorkSyncJournal.SCHEMA,
        "source_host": "DESKTOP-ODAQN0D",
        "source_sequence": 1,
        "previous_hash": WorkSyncJournal.GENESIS,
        "event_type": "revision.created",
        "work_code": "",
        "revision_id": "",
        "payload": {"value": 999},
    }
    forked = dict(body)
    forked["event_hash"] = WorkSyncJournal._event_hash(body)
    assert forked["event_hash"] != original["event_hash"]
    path.write_text(json.dumps(forked, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(WorkSyncImportError, match="SOURCE_FORK"):
        importer.import_journal(journal)


def test_importer_rejects_source_truncation_below_cursor(tmp_path):
    path = tmp_path / "o87.jsonl"
    journal = WorkSyncJournal(path, source_host="DESKTOP-O87")
    first = journal.append(event_type="revision.created", payload={})
    journal.append(event_type="revision.status", payload={"status": "executing"})
    importer = WorkSyncImporter(tmp_path / "state")
    importer.import_journal(journal)

    path.write_text(json.dumps(first, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(WorkSyncImportError, match="SOURCE_TRUNCATION"):
        importer.import_journal(journal)
