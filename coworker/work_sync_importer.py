"""Verified importer for replicated OpenWorker host journals.

The importer is deliberately transport- and WorkLedger-neutral.  It verifies a
complete source journal, compares it with the durable per-source cursor, applies
only unseen events, and advances the cursor after each successfully applied
event.  Replays are idempotent; source forks, truncation, gaps, or cursor drift
fail closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .work_sync_journal import WorkSyncJournal, WorkSyncJournalError


class WorkSyncImportError(RuntimeError):
    pass


ApplyEvent = Callable[[Mapping[str, Any]], None]


class WorkSyncImporter:
    CURSOR_SCHEMA = "openworker-work-sync-import-cursor/v1"

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _source_key(source_host: str) -> str:
        host = str(source_host or "").strip()
        if not host:
            raise WorkSyncImportError("source_host is required")
        return hashlib.sha256(host.encode("utf-8")).hexdigest()[:24]

    def cursor_path(self, source_host: str) -> Path:
        return self.state_root / f"{self._source_key(source_host)}.json"

    def load_cursor(self, source_host: str) -> dict[str, Any]:
        host = str(source_host or "").strip()
        path = self.cursor_path(host)
        if not path.exists():
            return {
                "schema": self.CURSOR_SCHEMA,
                "source_host": host,
                "source_sequence": 0,
                "event_hash": WorkSyncJournal.GENESIS,
            }
        try:
            cursor = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkSyncImportError(f"invalid sync cursor for {host}: {exc}") from exc
        if cursor.get("schema") != self.CURSOR_SCHEMA:
            raise WorkSyncImportError(f"unsupported sync cursor schema for {host}")
        if str(cursor.get("source_host") or "") != host:
            raise WorkSyncImportError("sync cursor source_host mismatch")
        sequence = int(cursor.get("source_sequence") or 0)
        event_hash = str(cursor.get("event_hash") or "").strip().lower()
        if sequence < 0 or len(event_hash) != 64:
            raise WorkSyncImportError("sync cursor is malformed")
        return {
            "schema": self.CURSOR_SCHEMA,
            "source_host": host,
            "source_sequence": sequence,
            "event_hash": event_hash,
        }

    def _write_cursor(self, cursor: Mapping[str, Any]) -> None:
        path = self.cursor_path(str(cursor.get("source_host") or ""))
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(dict(cursor), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)

    def import_journal(
        self,
        journal: WorkSyncJournal,
        *,
        apply_event: ApplyEvent | None = None,
    ) -> dict[str, Any]:
        rows = journal.read_all()
        source_host = journal.source_host
        if rows and str(rows[0].get("source_host") or "") != source_host:
            raise WorkSyncImportError("journal source_host does not match importer source")

        cursor = self.load_cursor(source_host)
        sequence = int(cursor["source_sequence"])
        cursor_hash = str(cursor["event_hash"])
        if sequence > len(rows):
            raise WorkSyncImportError(
                f"SOURCE_TRUNCATION source={source_host} cursor_sequence={sequence} journal_length={len(rows)}"
            )
        if sequence == 0:
            if cursor_hash != WorkSyncJournal.GENESIS:
                raise WorkSyncImportError("sync cursor genesis hash mismatch")
        else:
            authoritative = str(rows[sequence - 1].get("event_hash") or "").lower()
            if authoritative != cursor_hash:
                raise WorkSyncImportError(
                    f"SOURCE_FORK source={source_host} sequence={sequence} cursor_hash={cursor_hash} journal_hash={authoritative}"
                )

        imported = 0
        for row in rows[sequence:]:
            expected_sequence = int(cursor["source_sequence"]) + 1
            row_sequence = int(row.get("source_sequence") or 0)
            previous_hash = str(row.get("previous_hash") or "").lower()
            if row_sequence != expected_sequence:
                raise WorkSyncImportError(
                    f"SOURCE_SEQUENCE_GAP source={source_host} expected={expected_sequence} actual={row_sequence}"
                )
            if previous_hash != str(cursor["event_hash"]):
                raise WorkSyncImportError(
                    f"SOURCE_FORK source={source_host} sequence={row_sequence} previous_hash={previous_hash} cursor_hash={cursor['event_hash']}"
                )
            if apply_event is not None:
                apply_event(row)
            cursor = {
                "schema": self.CURSOR_SCHEMA,
                "source_host": source_host,
                "source_sequence": row_sequence,
                "event_hash": str(row.get("event_hash") or "").lower(),
            }
            self._write_cursor(cursor)
            imported += 1

        return {
            "source_host": source_host,
            "journal_events": len(rows),
            "imported_events": imported,
            "cursor": cursor,
        }


__all__ = ["WorkSyncImporter", "WorkSyncImportError", "ApplyEvent"]
