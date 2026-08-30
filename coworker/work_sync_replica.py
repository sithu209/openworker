"""Deterministic read-only replica store for verified multi-host work events.

Remote journal events must not directly mutate a job's authoritative WorkLedger
because JobBinding fixes that authority to an owner host.  This store materializes
verified replicated events into a queryable SQLite index while preserving source
identity and failing closed on any source-sequence conflict.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping


class WorkSyncReplicaError(RuntimeError):
    pass


class WorkSyncReplicaStore:
    SCHEMA = "openworker-work-sync-replica/v1"

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS replica_events (
                    source_host TEXT NOT NULL,
                    source_sequence INTEGER NOT NULL,
                    event_hash TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    work_code TEXT NOT NULL DEFAULT '',
                    revision_id TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(source_host, source_sequence),
                    UNIQUE(event_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_replica_work
                    ON replica_events(work_code, source_host, source_sequence);
                CREATE INDEX IF NOT EXISTS idx_replica_revision
                    ON replica_events(revision_id, source_host, source_sequence);
                """
            )

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _required(value: Any, name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise WorkSyncReplicaError(f"{name} is required")
        return normalized

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    def project(self, event: Mapping[str, Any]) -> dict[str, Any]:
        source_host = self._required(event.get("source_host"), "source_host")
        sequence = int(event.get("source_sequence") or 0)
        if sequence <= 0:
            raise WorkSyncReplicaError("source_sequence must be > 0")
        event_hash = self._required(event.get("event_hash"), "event_hash").lower()
        previous_hash = self._required(event.get("previous_hash"), "previous_hash").lower()
        event_type = self._required(event.get("event_type"), "event_type")
        if len(event_hash) != 64 or len(previous_hash) != 64:
            raise WorkSyncReplicaError("event hashes must be 64-character digests")
        work_code = str(event.get("work_code") or "").strip()
        revision_id = str(event.get("revision_id") or "").strip()
        payload_json = self._json(dict(event.get("payload") or {}))

        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT * FROM replica_events WHERE source_host = ? AND source_sequence = ?",
                (source_host, sequence),
            ).fetchone()
            if existing:
                same = (
                    existing["event_hash"] == event_hash
                    and existing["previous_hash"] == previous_hash
                    and existing["event_type"] == event_type
                    and existing["work_code"] == work_code
                    and existing["revision_id"] == revision_id
                    and existing["payload_json"] == payload_json
                )
                if not same:
                    raise WorkSyncReplicaError(
                        f"REPLICA_EVENT_CONFLICT source={source_host} sequence={sequence} "
                        f"stored_hash={existing['event_hash']} candidate_hash={event_hash}"
                    )
                return self._decode(existing)
            try:
                self._conn.execute(
                    """INSERT INTO replica_events
                       (source_host, source_sequence, event_hash, previous_hash, event_type, work_code, revision_id, payload_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (source_host, sequence, event_hash, previous_hash, event_type, work_code, revision_id, payload_json),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkSyncReplicaError(
                    f"REPLICA_EVENT_CONFLICT duplicate event_hash={event_hash} source={source_host} sequence={sequence}"
                ) from exc
            row = self._conn.execute(
                "SELECT * FROM replica_events WHERE source_host = ? AND source_sequence = ?",
                (source_host, sequence),
            ).fetchone()
            assert row is not None
            return self._decode(row)

    def list_events(self, *, source_host: str = "", work_code: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if source_host:
            clauses.append("source_host = ?")
            params.append(source_host)
        if work_code:
            clauses.append("work_code = ?")
            params.append(work_code)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._conn.execute(
            "SELECT * FROM replica_events" + where + " ORDER BY source_host, source_sequence",
            tuple(params),
        ).fetchall()
        return [self._decode(row) for row in rows]

    def source_heads(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT e.source_host, e.source_sequence, e.event_hash
               FROM replica_events e
               JOIN (
                    SELECT source_host, MAX(source_sequence) AS max_sequence
                    FROM replica_events GROUP BY source_host
               ) h ON h.source_host = e.source_host AND h.max_sequence = e.source_sequence
               ORDER BY e.source_host"""
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json") or "{}")
        return value


__all__ = ["WorkSyncReplicaStore", "WorkSyncReplicaError"]
