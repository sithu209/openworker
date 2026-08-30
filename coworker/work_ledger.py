"""Durable Git-like work ledger for OpenWorker jobs.

A work behaves like a tiny repository: revisions form an immutable parent chain,
artifacts/checks belong to a revision, acceptance moves a protected pointer, and
rework always creates a child revision instead of rewriting history.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

_TERMINAL_REVISION_STATUSES = {"accepted", "rework_required", "failed", "superseded"}
_MUTABLE_REVISION_STATUSES = {"open", "executing", "verifying", "blocked"}
_VALID_REVISION_KINDS = {"initial", "progress", "tuning", "rework", "acceptance", "delivery", "acceptance_import"}
_VALID_CHECK_STATUSES = {"pending", "passed", "failed", "skipped", "blocked"}


class WorkLedgerError(RuntimeError):
    """Raised when a work-ledger invariant would be violated."""


class WorkLedger:
    """SQLite-backed append-only work history with protected HEAD/acceptance pointers."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS works (
                    work_id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    workspace TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    head_revision_id TEXT,
                    accepted_revision_id TEXT,
                    delivered_revision_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS work_revisions (
                    revision_id TEXT PRIMARY KEY,
                    work_id TEXT NOT NULL REFERENCES works(work_id),
                    revision_no INTEGER NOT NULL,
                    parent_revision_id TEXT REFERENCES work_revisions(revision_id),
                    rework_of_revision_id TEXT REFERENCES work_revisions(revision_id),
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    goal TEXT NOT NULL DEFAULT '',
                    plan_json TEXT NOT NULL DEFAULT '{}',
                    reason TEXT NOT NULL DEFAULT '',
                    gap_owner_repo TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(work_id, revision_no)
                );

                CREATE TABLE IF NOT EXISTS work_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES work_revisions(revision_id),
                    logical_name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    verification_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(revision_id, logical_name)
                );

                CREATE TABLE IF NOT EXISTS work_checks (
                    check_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES work_revisions(revision_id),
                    name TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(revision_id, name)
                );

                CREATE TABLE IF NOT EXISTS work_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL REFERENCES work_revisions(revision_id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_work_revisions_work
                    ON work_revisions(work_id, revision_no);
                CREATE INDEX IF NOT EXISTS idx_work_events_revision
                    ON work_events(revision_id, event_id);
                """
            )

    def close(self) -> None:
        self._conn.close()

    def create_work(
        self,
        *,
        code: str,
        title: str,
        workspace: str = "",
        goal: str = "",
        plan: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        code = self._required(code, "code")
        title = self._required(title, "title")
        work_id = f"wrk_{uuid.uuid4().hex}"
        revision_id = f"rev_{uuid.uuid4().hex}"
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO works(work_id, code, title, workspace, head_revision_id) VALUES (?, ?, ?, ?, ?)",
                    (work_id, code, title, workspace.strip(), revision_id),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkLedgerError(f"work code already exists: {code}") from exc
            self._conn.execute(
                """INSERT INTO work_revisions
                   (revision_id, work_id, revision_no, kind, status, goal, plan_json)
                   VALUES (?, ?, 1, 'initial', 'open', ?, ?)""",
                (revision_id, work_id, goal.strip(), self._json(plan or {})),
            )
            self._event(revision_id, "revision.created", {"kind": "initial", "revision_no": 1})
        return self.get_work(work_id)

    def open_revision(
        self,
        work_id: str,
        *,
        kind: str = "progress",
        goal: str = "",
        plan: Mapping[str, Any] | None = None,
        reason: str = "",
        gap_owner_repo: str = "",
        parent_revision_id: str | None = None,
        rework_of_revision_id: str | None = None,
    ) -> dict[str, Any]:
        if kind not in _VALID_REVISION_KINDS:
            raise WorkLedgerError(f"unsupported revision kind: {kind}")
        with self._lock, self._conn:
            work = self._work_row(work_id)
            parent_id = parent_revision_id or work["head_revision_id"]
            if not parent_id:
                raise WorkLedgerError("work has no HEAD revision")
            parent = self._revision_row(parent_id)
            if parent["work_id"] != work_id:
                raise WorkLedgerError("parent revision belongs to another work")
            if rework_of_revision_id:
                rework = self._revision_row(rework_of_revision_id)
                if rework["work_id"] != work_id:
                    raise WorkLedgerError("rework target belongs to another work")
            if kind == "rework" and not rework_of_revision_id:
                rework_of_revision_id = parent_id
            next_no = int(
                self._conn.execute(
                    "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM work_revisions WHERE work_id = ?",
                    (work_id,),
                ).fetchone()[0]
            )
            revision_id = f"rev_{uuid.uuid4().hex}"
            self._conn.execute(
                """INSERT INTO work_revisions
                   (revision_id, work_id, revision_no, parent_revision_id,
                    rework_of_revision_id, kind, status, goal, plan_json, reason, gap_owner_repo)
                   VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
                (
                    revision_id,
                    work_id,
                    next_no,
                    parent_id,
                    rework_of_revision_id,
                    kind,
                    goal.strip(),
                    self._json(plan or {}),
                    reason.strip(),
                    gap_owner_repo.strip(),
                ),
            )
            self._conn.execute(
                "UPDATE works SET head_revision_id = ?, status = 'open', updated_at = CURRENT_TIMESTAMP WHERE work_id = ?",
                (revision_id, work_id),
            )
            self._event(
                revision_id,
                "revision.created",
                {"kind": kind, "revision_no": next_no, "parent_revision_id": parent_id, "rework_of_revision_id": rework_of_revision_id},
            )
        return self.get_revision(revision_id)

    def set_revision_status(self, revision_id: str, status: str, *, reason: str = "") -> dict[str, Any]:
        allowed = _MUTABLE_REVISION_STATUSES | {"failed"}
        if status not in allowed:
            raise WorkLedgerError("accepted/rework-required states are controlled by dedicated gates")
        with self._lock, self._conn:
            row = self._revision_row(revision_id)
            if row["status"] in _TERMINAL_REVISION_STATUSES:
                raise WorkLedgerError(f"revision is immutable after terminal status {row['status']}")
            self._conn.execute("UPDATE work_revisions SET status = ?, reason = CASE WHEN ? <> '' THEN ? ELSE reason END WHERE revision_id = ?", (status, reason.strip(), reason.strip(), revision_id))
            self._conn.execute("UPDATE works SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE work_id = ? AND head_revision_id = ?", (status, row["work_id"], revision_id))
            self._event(revision_id, "revision.status", {"status": status, "reason": reason.strip()})
        return self.get_revision(revision_id)

    def add_artifact(
        self,
        revision_id: str,
        *,
        logical_name: str,
        path: str,
        sha256: str,
        size_bytes: int,
        provenance: Mapping[str, Any] | None = None,
        verification_status: str = "pending",
    ) -> dict[str, Any]:
        logical_name = self._required(logical_name, "logical_name")
        path = self._required(path, "path")
        sha256 = self._required(sha256, "sha256").lower()
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise WorkLedgerError("sha256 must be a 64-character lowercase/uppercase hex digest")
        if int(size_bytes) <= 0:
            raise WorkLedgerError("artifact size_bytes must be > 0")
        with self._lock, self._conn:
            self._assert_revision_mutable(revision_id)
            artifact_id = f"art_{uuid.uuid4().hex}"
            try:
                self._conn.execute(
                    """INSERT INTO work_artifacts
                       (artifact_id, revision_id, logical_name, path, sha256, size_bytes, provenance_json, verification_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (artifact_id, revision_id, logical_name, path, sha256, int(size_bytes), self._json(provenance or {}), verification_status),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkLedgerError(f"artifact {logical_name!r} already exists in revision; create a new revision to replace it") from exc
            self._event(revision_id, "artifact.added", {"artifact_id": artifact_id, "logical_name": logical_name, "sha256": sha256, "size_bytes": int(size_bytes)})
        return self._artifact(artifact_id)

    def add_file_artifact(
        self,
        revision_id: str,
        *,
        logical_name: str,
        path: str | Path,
        provenance: Mapping[str, Any] | None = None,
        verification_status: str = "passed",
    ) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.is_file():
            raise WorkLedgerError(f"artifact does not exist: {file_path}")
        size = file_path.stat().st_size
        if size <= 0:
            raise WorkLedgerError(f"artifact is empty: {file_path}")
        digest = hashlib.sha256()
        with file_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return self.add_artifact(
            revision_id,
            logical_name=logical_name,
            path=str(file_path.resolve()),
            sha256=digest.hexdigest(),
            size_bytes=size,
            provenance=provenance,
            verification_status=verification_status,
        )

    def set_check(
        self,
        revision_id: str,
        *,
        name: str,
        status: str,
        required: bool = True,
        evidence: Mapping[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        name = self._required(name, "name")
        if status not in _VALID_CHECK_STATUSES:
            raise WorkLedgerError(f"unsupported check status: {status}")
        with self._lock, self._conn:
            self._assert_revision_mutable(revision_id)
            existing = self._conn.execute("SELECT check_id FROM work_checks WHERE revision_id = ? AND name = ?", (revision_id, name)).fetchone()
            if existing:
                self._conn.execute(
                    """UPDATE work_checks SET required = ?, status = ?, evidence_json = ?, reason = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE check_id = ?""",
                    (int(bool(required)), status, self._json(evidence or {}), reason.strip(), existing["check_id"]),
                )
                check_id = existing["check_id"]
            else:
                check_id = f"chk_{uuid.uuid4().hex}"
                self._conn.execute(
                    """INSERT INTO work_checks(check_id, revision_id, name, required, status, evidence_json, reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (check_id, revision_id, name, int(bool(required)), status, self._json(evidence or {}), reason.strip()),
                )
            self._event(revision_id, "check.updated", {"check_id": check_id, "name": name, "required": bool(required), "status": status, "reason": reason.strip()})
        return self._check(check_id)

    def request_rework(
        self,
        revision_id: str,
        *,
        reason: str,
        gap_owner_repo: str = "",
        changed_contracts: Sequence[str] = (),
        verification_plan: Sequence[str] = (),
    ) -> dict[str, Any]:
        reason = self._required(reason, "reason")
        with self._lock, self._conn:
            row = self._revision_row(revision_id)
            if row["status"] == "accepted":
                raise WorkLedgerError("accepted revision is immutable; open a new child revision for regression/rework")
            if row["status"] in {"failed", "superseded"}:
                raise WorkLedgerError(f"cannot request rework from terminal revision status {row['status']}")
            self._conn.execute("UPDATE work_revisions SET status = 'rework_required', reason = ?, gap_owner_repo = ? WHERE revision_id = ?", (reason, gap_owner_repo.strip(), revision_id))
            self._conn.execute("UPDATE works SET status = 'rework_required', updated_at = CURRENT_TIMESTAMP WHERE work_id = ?", (row["work_id"],))
            self._event(revision_id, "rework.required", {"reason": reason, "gap_owner_repo": gap_owner_repo.strip(), "changed_contracts": list(changed_contracts), "verification_plan": list(verification_plan)})
        return self.get_revision(revision_id)

    def open_rework(
        self,
        revision_id: str,
        *,
        goal: str = "",
        plan: Mapping[str, Any] | None = None,
        reason: str = "",
        gap_owner_repo: str = "",
    ) -> dict[str, Any]:
        source = self._revision_row(revision_id)
        if source["status"] != "rework_required":
            raise WorkLedgerError("source revision must be REWORK_REQUIRED before opening rework")
        return self.open_revision(
            source["work_id"],
            kind="rework",
            goal=goal,
            plan=plan,
            reason=reason or source["reason"],
            gap_owner_repo=gap_owner_repo or source["gap_owner_repo"],
            parent_revision_id=revision_id,
            rework_of_revision_id=revision_id,
        )

    def accept_revision(self, revision_id: str) -> dict[str, Any]:
        with self._lock, self._conn:
            row = self._revision_row(revision_id)
            if row["status"] in _TERMINAL_REVISION_STATUSES:
                if row["status"] == "accepted":
                    return self.get_revision(revision_id)
                raise WorkLedgerError(f"cannot accept terminal revision status {row['status']}")
            required_checks = self._conn.execute("SELECT name, status FROM work_checks WHERE revision_id = ? AND required = 1 ORDER BY name", (revision_id,)).fetchall()
            if not required_checks:
                raise WorkLedgerError("acceptance requires at least one required check")
            bad = [f"{c['name']}={c['status']}" for c in required_checks if c["status"] != "passed"]
            if bad:
                raise WorkLedgerError("required checks are not all passed: " + ", ".join(bad))
            self._conn.execute("UPDATE work_revisions SET status = 'accepted' WHERE revision_id = ?", (revision_id,))
            self._conn.execute("""UPDATE works SET head_revision_id = ?, accepted_revision_id = ?, status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE work_id = ?""", (revision_id, revision_id, row["work_id"]))
            self._event(revision_id, "revision.accepted", {"required_checks": [c["name"] for c in required_checks]})
        return self.get_revision(revision_id)

    def deliver_revision(self, revision_id: str, *, delivery: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._lock, self._conn:
            row = self._revision_row(revision_id)
            if row["status"] != "accepted":
                raise WorkLedgerError("delivery may only point to an accepted revision")
            self._conn.execute("UPDATE works SET delivered_revision_id = ?, status = 'delivered', updated_at = CURRENT_TIMESTAMP WHERE work_id = ?", (revision_id, row["work_id"]))
            self._event(revision_id, "revision.delivered", dict(delivery or {}))
        return self.get_work(row["work_id"])

    def move_head_to_accepted(self, work_id: str) -> dict[str, Any]:
        """Move HEAD to the last accepted revision without deleting newer history."""
        with self._lock, self._conn:
            work = self._work_row(work_id)
            accepted = work["accepted_revision_id"]
            if not accepted:
                raise WorkLedgerError("work has no accepted revision")
            self._conn.execute("UPDATE works SET head_revision_id = ?, status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE work_id = ?", (accepted, work_id))
            self._event(accepted, "head.moved_to_accepted", {"previous_head_revision_id": work["head_revision_id"]})
        return self.get_work(work_id)

    def get_work(self, work_id: str) -> dict[str, Any]:
        row = self._work_row(work_id)
        return dict(row)

    def get_work_by_code(self, code: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM works WHERE code = ?", (code,)).fetchone()
        if not row:
            raise WorkLedgerError(f"unknown work code: {code}")
        return dict(row)

    def get_revision(self, revision_id: str) -> dict[str, Any]:
        row = dict(self._revision_row(revision_id))
        row["plan"] = self._loads(row.pop("plan_json"))
        return row

    def list_revisions(self, work_id: str) -> list[dict[str, Any]]:
        self._work_row(work_id)
        rows = self._conn.execute("SELECT revision_id FROM work_revisions WHERE work_id = ? ORDER BY revision_no", (work_id,)).fetchall()
        return [self.get_revision(row["revision_id"]) for row in rows]

    def snapshot(self, work_id: str) -> dict[str, Any]:
        work = self.get_work(work_id)
        revisions: list[dict[str, Any]] = []
        for revision in self.list_revisions(work_id):
            rid = revision["revision_id"]
            revision["artifacts"] = [self._decode_artifact(dict(r)) for r in self._conn.execute("SELECT * FROM work_artifacts WHERE revision_id = ? ORDER BY created_at, artifact_id", (rid,)).fetchall()]
            revision["checks"] = [self._decode_check(dict(r)) for r in self._conn.execute("SELECT * FROM work_checks WHERE revision_id = ? ORDER BY name", (rid,)).fetchall()]
            revision["events"] = [self._decode_event(dict(r)) for r in self._conn.execute("SELECT * FROM work_events WHERE revision_id = ? ORDER BY event_id", (rid,)).fetchall()]
            revisions.append(revision)
        return {"schema": "openworker-work-ledger/v1", "work": work, "revisions": revisions}

    def _assert_revision_mutable(self, revision_id: str) -> sqlite3.Row:
        row = self._revision_row(revision_id)
        if row["status"] not in _MUTABLE_REVISION_STATUSES:
            raise WorkLedgerError(f"revision {revision_id} is immutable in status {row['status']}; create a child revision")
        return row

    def _work_row(self, work_id: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM works WHERE work_id = ?", (work_id,)).fetchone()
        if not row:
            raise WorkLedgerError(f"unknown work: {work_id}")
        return row

    def _revision_row(self, revision_id: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM work_revisions WHERE revision_id = ?", (revision_id,)).fetchone()
        if not row:
            raise WorkLedgerError(f"unknown revision: {revision_id}")
        return row

    def _artifact(self, artifact_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM work_artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
        if not row:
            raise WorkLedgerError(f"unknown artifact: {artifact_id}")
        return self._decode_artifact(dict(row))

    def _check(self, check_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM work_checks WHERE check_id = ?", (check_id,)).fetchone()
        if not row:
            raise WorkLedgerError(f"unknown check: {check_id}")
        return self._decode_check(dict(row))

    def _event(self, revision_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        self._conn.execute("INSERT INTO work_events(revision_id, event_type, payload_json) VALUES (?, ?, ?)", (revision_id, event_type, self._json(payload)))

    @staticmethod
    def _required(value: str, name: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise WorkLedgerError(f"{name} is required")
        return normalized

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _loads(value: str) -> Any:
        try:
            return json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}

    def _decode_artifact(self, row: dict[str, Any]) -> dict[str, Any]:
        row["provenance"] = self._loads(row.pop("provenance_json"))
        return row

    def _decode_check(self, row: dict[str, Any]) -> dict[str, Any]:
        row["required"] = bool(row["required"])
        row["evidence"] = self._loads(row.pop("evidence_json"))
        return row

    def _decode_event(self, row: dict[str, Any]) -> dict[str, Any]:
        row["payload"] = self._loads(row.pop("payload_json"))
        return row
