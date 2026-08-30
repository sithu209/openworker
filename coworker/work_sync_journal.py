"""Hash-chained append-only journal for multi-host OpenWorker synchronization.

This module does not replace WorkLedger.  It provides a portable immutable event
stream that each host can append locally and later replicate/merge without
requiring one always-online SQLite authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


class WorkSyncJournalError(RuntimeError):
    pass


class WorkSyncJournal:
    SCHEMA = "openworker-work-sync-journal/v1"
    GENESIS = "0" * 64

    def __init__(self, path: str | Path, *, source_host: str) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.source_host = str(source_host or "").strip()
        if not self.source_host:
            raise WorkSyncJournalError("source_host is required")

    @staticmethod
    def _canonical(value: Mapping[str, Any]) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    @classmethod
    def _event_hash(cls, event_without_hash: Mapping[str, Any]) -> str:
        return hashlib.sha256(cls._canonical(event_without_hash)).hexdigest()

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise WorkSyncJournalError(f"invalid journal JSON at line {number}: {exc}") from exc
            rows.append(row)
        self.verify(rows)
        return rows

    def append(self, *, event_type: str, payload: Mapping[str, Any], work_code: str = "", revision_id: str = "") -> dict[str, Any]:
        event_type = str(event_type or "").strip()
        if not event_type:
            raise WorkSyncJournalError("event_type is required")
        rows = self.read_all()
        sequence = len(rows) + 1
        previous_hash = rows[-1]["event_hash"] if rows else self.GENESIS
        body = {
            "schema": self.SCHEMA,
            "source_host": self.source_host,
            "source_sequence": sequence,
            "previous_hash": previous_hash,
            "event_type": event_type,
            "work_code": str(work_code or "").strip(),
            "revision_id": str(revision_id or "").strip(),
            "payload": dict(payload or {}),
        }
        row = dict(body)
        row["event_hash"] = self._event_hash(body)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        return row

    @classmethod
    def verify(cls, rows: Iterable[Mapping[str, Any]]) -> None:
        previous = cls.GENESIS
        expected_sequence = 1
        source_host: str | None = None
        seen_hashes: set[str] = set()
        for row in rows:
            current = dict(row)
            event_hash = str(current.pop("event_hash", "")).strip().lower()
            if len(event_hash) != 64:
                raise WorkSyncJournalError("journal event_hash is missing or malformed")
            if current.get("schema") != cls.SCHEMA:
                raise WorkSyncJournalError("unsupported journal schema")
            host = str(current.get("source_host") or "").strip()
            if not host:
                raise WorkSyncJournalError("journal source_host is required")
            if source_host is None:
                source_host = host
            elif source_host != host:
                raise WorkSyncJournalError("one journal file may contain only one source_host")
            if int(current.get("source_sequence") or 0) != expected_sequence:
                raise WorkSyncJournalError("journal source_sequence is not contiguous")
            if str(current.get("previous_hash") or "").lower() != previous:
                raise WorkSyncJournalError("journal previous_hash chain mismatch")
            calculated = cls._event_hash(current)
            if calculated != event_hash:
                raise WorkSyncJournalError("journal event hash mismatch")
            if event_hash in seen_hashes:
                raise WorkSyncJournalError("duplicate journal event hash")
            seen_hashes.add(event_hash)
            previous = event_hash
            expected_sequence += 1

    def cursor(self) -> dict[str, Any]:
        rows = self.read_all()
        return {
            "schema": "openworker-work-sync-cursor/v1",
            "source_host": self.source_host,
            "source_sequence": len(rows),
            "event_hash": rows[-1]["event_hash"] if rows else self.GENESIS,
        }


__all__ = ["WorkSyncJournal", "WorkSyncJournalError"]
