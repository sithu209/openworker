from __future__ import annotations

import pytest

from coworker.work_sync_importer import WorkSyncImporter
from coworker.work_sync_journal import WorkSyncJournal
from coworker.work_sync_replica import WorkSyncReplicaError, WorkSyncReplicaStore


def test_importer_projects_verified_events_into_replica_store(tmp_path):
    journal = WorkSyncJournal(tmp_path / "ul7.jsonl", source_host="DESKTOP-UL7V2VV")
    first = journal.append(event_type="revision.created", work_code="OWJ-1", revision_id="rev-1", payload={"kind": "initial"})
    second = journal.append(event_type="artifact.added", work_code="OWJ-1", revision_id="rev-1", payload={"sha256": "a" * 64})
    importer = WorkSyncImporter(tmp_path / "cursor-state")
    replica = WorkSyncReplicaStore(tmp_path / "replica.sqlite")
    try:
        result = importer.import_journal(journal, apply_event=replica.project)
        assert result["imported_events"] == 2
        events = replica.list_events(work_code="OWJ-1")
        assert [item["event_hash"] for item in events] == [first["event_hash"], second["event_hash"]]
        assert replica.source_heads() == [
            {
                "source_host": "DESKTOP-UL7V2VV",
                "source_sequence": 2,
                "event_hash": second["event_hash"],
            }
        ]
        replay = importer.import_journal(journal, apply_event=replica.project)
        assert replay["imported_events"] == 0
        assert len(replica.list_events()) == 2
    finally:
        replica.close()


def test_replica_same_source_sequence_is_idempotent_only_for_exact_event(tmp_path):
    journal = WorkSyncJournal(tmp_path / "oda.jsonl", source_host="DESKTOP-ODAQN0D")
    row = journal.append(event_type="revision.created", work_code="OWJ-2", revision_id="rev-a", payload={"value": 1})
    replica = WorkSyncReplicaStore(tmp_path / "replica.sqlite")
    try:
        first = replica.project(row)
        second = replica.project(row)
        assert first == second
        conflict = dict(row)
        conflict["payload"] = {"value": 999}
        with pytest.raises(WorkSyncReplicaError, match="REPLICA_EVENT_CONFLICT"):
            replica.project(conflict)
        stored = replica.list_events(source_host="DESKTOP-ODAQN0D")
        assert len(stored) == 1
        assert stored[0]["payload"] == {"value": 1}
    finally:
        replica.close()


def test_replica_keeps_multiple_source_heads_independent(tmp_path):
    ul7 = WorkSyncJournal(tmp_path / "ul7.jsonl", source_host="DESKTOP-UL7V2VV")
    oda = WorkSyncJournal(tmp_path / "oda.jsonl", source_host="DESKTOP-ODAQN0D")
    ul7_row = ul7.append(event_type="revision.status", work_code="OWJ-X", payload={"status": "executing"})
    oda_row = oda.append(event_type="revision.status", work_code="OWJ-Y", payload={"status": "verifying"})
    replica = WorkSyncReplicaStore(tmp_path / "replica.sqlite")
    try:
        replica.project(ul7_row)
        replica.project(oda_row)
        heads = {item["source_host"]: item for item in replica.source_heads()}
        assert heads["DESKTOP-UL7V2VV"]["event_hash"] == ul7_row["event_hash"]
        assert heads["DESKTOP-ODAQN0D"]["event_hash"] == oda_row["event_hash"]
    finally:
        replica.close()
