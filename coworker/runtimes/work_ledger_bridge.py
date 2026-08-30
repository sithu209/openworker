"""Bind every fixed OpenWorker job to the Git-like WorkLedger.

The bridge keeps lifecycle ownership in OpenWorker: creating a JobBinding creates
its durable mini-Git ledger automatically. Higher-level runtimes attach physical
artifacts, verification failures and rework without case-specific bookkeeping.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from ..work_ledger import WorkLedger, WorkLedgerError
from .job_binding import JobBinding

_FAILURE_KINDS = {"failed", "failure", "rework_required", "rework-required"}
_FAILURE_STATUSES = {"failed", "failure", "rework_required", "rework-required"}
_REPAIR_KINDS = {"repaired", "repair", "progress", "executing", "retry"}


class WorkLedgerBridge:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.root = self.workspace / ".openworker"
        self.path = self.root / "work-ledger.sqlite"
        self.project_events_path = self.root / "project-knowledge.jsonl"
        self.synced_events_path = self.root / "work-ledger-project-events.jsonl"

    def ensure(self, binding: JobBinding, *, goal: str = "") -> dict[str, Any]:
        ledger = WorkLedger(self.path)
        try:
            try:
                return ledger.get_work_by_code(binding.job_code)
            except WorkLedgerError:
                return ledger.create_work(
                    code=binding.job_code,
                    title=f"{binding.project_code} / {binding.job_code}",
                    workspace=str(self.workspace),
                    goal=goal,
                    plan={
                        "project_id": binding.project_id,
                        "project_code": binding.project_code,
                        "job_id": binding.job_id,
                        "assigned_host": binding.assigned_host,
                    },
                )
        finally:
            ledger.close()

    def snapshot(self, binding: JobBinding) -> dict[str, Any]:
        ledger = WorkLedger(self.path)
        try:
            work = ledger.get_work_by_code(binding.job_code)
            return ledger.snapshot(work["work_id"])
        finally:
            ledger.close()

    @staticmethod
    def _file_identity(path: Path) -> tuple[str, int, str]:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise WorkLedgerError(f"artifact does not exist: {resolved}")
        size = resolved.stat().st_size
        if size <= 0:
            raise WorkLedgerError(f"artifact is empty: {resolved}")
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest(), int(size), str(resolved)

    @staticmethod
    def _existing_artifact(ledger: WorkLedger, work_id: str, revision_id: str, logical_name: str) -> dict[str, Any] | None:
        snapshot = ledger.snapshot(work_id)
        revision = next((item for item in snapshot["revisions"] if item["revision_id"] == revision_id), None)
        if revision is None:
            raise WorkLedgerError(f"revision disappeared during artifact replay: {revision_id}")
        matches = [item for item in revision["artifacts"] if item["logical_name"] == logical_name]
        if len(matches) > 1:
            raise WorkLedgerError(f"ledger invariant broken: duplicate logical artifact records for {logical_name!r}")
        return matches[0] if matches else None

    def _assert_replay_identity(
        self,
        ledger: WorkLedger,
        *,
        work_id: str,
        revision_id: str,
        logical_name: str,
        candidate: Path,
    ) -> None:
        existing = self._existing_artifact(ledger, work_id, revision_id, logical_name)
        if existing is None:
            raise WorkLedgerError(
                f"artifact {logical_name!r} reported duplicate but authoritative record is unavailable"
            )
        sha256, size_bytes, canonical_path = self._file_identity(candidate)
        expected_path = str(Path(str(existing["path"])).expanduser().resolve())
        if (
            str(existing["sha256"]).lower() == sha256.lower()
            and int(existing["size_bytes"]) == size_bytes
            and expected_path == canonical_path
        ):
            return
        raise WorkLedgerError(
            "ARTIFACT_REPLAY_CONFLICT: same logical artifact changed within one revision; "
            f"logical_name={logical_name!r} "
            f"existing_sha256={existing['sha256']} candidate_sha256={sha256} "
            f"existing_size={existing['size_bytes']} candidate_size={size_bytes} "
            f"existing_path={expected_path!r} candidate_path={canonical_path!r}; "
            "create a child revision for replacement bytes"
        )

    def sync_pending_project_events(self, binding: JobBinding) -> int:
        """Replay unsynced ProjectKnowledge events into the WorkLedger.

        The sidecar contains only successfully projected event IDs. A crash between
        source append and ledger projection is therefore repaired on the next job
        load/resume/query instead of silently losing lifecycle history.
        """
        if not self.project_events_path.is_file():
            return 0
        synced: set[str] = set()
        if self.synced_events_path.is_file():
            for line in self.synced_events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except ValueError as exc:
                    raise WorkLedgerError(f"invalid work-ledger event sync sidecar: {exc}") from exc
                event_id = str(payload.get("event_id") or "").strip()
                if event_id:
                    synced.add(event_id)

        count = 0
        for number, line in enumerate(self.project_events_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except ValueError as exc:
                raise WorkLedgerError(f"invalid project knowledge event at line {number}: {exc}") from exc
            event_id = str(raw.get("event_id") or "").strip()
            if not event_id:
                raise WorkLedgerError(f"project knowledge event at line {number} has no event_id")
            if event_id in synced:
                continue
            self.sync_project_event(binding, SimpleNamespace(**raw))
            self.root.mkdir(parents=True, exist_ok=True)
            with self.synced_events_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"event_id": event_id}, ensure_ascii=False, sort_keys=True) + "\n")
            synced.add(event_id)
            count += 1
        return count

    def sync_project_event(self, binding: JobBinding, event: Any) -> dict[str, Any]:
        """Project one ProjectKnowledge event into the authoritative revision chain.

        Completion text never auto-accepts a revision. Only WorkLedger required
        checks may move the protected accepted pointer.
        """
        ledger = WorkLedger(self.path)
        try:
            try:
                work = ledger.get_work_by_code(binding.job_code)
            except WorkLedgerError:
                work = ledger.create_work(
                    code=binding.job_code,
                    title=f"{binding.project_code} / {binding.job_code}",
                    workspace=str(self.workspace),
                )

            head_id = str(work["head_revision_id"] or "")
            if not head_id:
                raise WorkLedgerError("work has no HEAD revision")
            head = ledger.get_revision(head_id)
            kind = str(getattr(event, "kind", "") or "").strip().lower()
            status = str(getattr(event, "status", "") or "").strip().lower()
            summary = str(getattr(event, "summary", "") or "").strip()
            details = dict(getattr(event, "details", {}) or {})

            if head["status"] == "rework_required" and kind in _REPAIR_KINDS:
                head = ledger.open_rework(
                    head_id,
                    goal=summary,
                    plan={"source_event_id": str(getattr(event, "event_id", "") or "")},
                    reason=head.get("reason", ""),
                    gap_owner_repo=head.get("gap_owner_repo", ""),
                )
                head_id = head["revision_id"]

            for index, ref in enumerate(tuple(getattr(event, "artifact_refs", ()) or ())):
                candidate = Path(str(ref)).expanduser()
                if not candidate.is_absolute():
                    candidate = self.workspace / candidate
                if not candidate.is_file() or candidate.stat().st_size <= 0:
                    continue
                logical_name = candidate.name or f"artifact-{index + 1}"
                try:
                    ledger.add_file_artifact(
                        head_id,
                        logical_name=logical_name,
                        path=candidate,
                        provenance={
                            "source": "ProjectKnowledgeStore",
                            "event_id": str(getattr(event, "event_id", "") or ""),
                            "capability_id": str(getattr(event, "capability_id", "") or ""),
                            "runtime_job_id": str(getattr(event, "runtime_job_id", "") or ""),
                        },
                        verification_status="passed",
                    )
                except WorkLedgerError as exc:
                    if "already exists in revision" not in str(exc):
                        raise
                    self._assert_replay_identity(
                        ledger,
                        work_id=work["work_id"],
                        revision_id=head_id,
                        logical_name=logical_name,
                        candidate=candidate,
                    )

            if kind in _FAILURE_KINDS or status in _FAILURE_STATUSES:
                current = ledger.get_revision(head_id)
                if current["status"] != "rework_required":
                    reason = summary or "project knowledge verification failure"
                    gap_owner_repo = str(details.get("gap_owner_repo") or details.get("owner_repo") or "").strip()
                    changed_contracts = tuple(str(v) for v in details.get("changed_contracts", ()) if str(v).strip())
                    verification_plan = tuple(str(v) for v in details.get("verification_plan", ()) if str(v).strip())
                    ledger.request_rework(
                        head_id,
                        reason=reason,
                        gap_owner_repo=gap_owner_repo,
                        changed_contracts=changed_contracts,
                        verification_plan=verification_plan,
                    )
            elif status in {"executing", "in_progress", "in-progress", "running"}:
                current = ledger.get_revision(head_id)
                if current["status"] in {"open", "blocked", "verifying"}:
                    ledger.set_revision_status(head_id, "executing", reason=summary)
            elif kind in {"completed", "accepted"} or status in {"completed", "accepted", "success", "succeeded"}:
                current = ledger.get_revision(head_id)
                if current["status"] in {"open", "executing", "blocked"}:
                    ledger.set_revision_status(head_id, "verifying", reason=summary)

            return ledger.snapshot(work["work_id"])
        finally:
            ledger.close()

    def add_file_artifact(
        self,
        binding: JobBinding,
        *,
        logical_name: str,
        path: str | Path,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ledger = WorkLedger(self.path)
        try:
            work = ledger.get_work_by_code(binding.job_code)
            revision_id = str(work["head_revision_id"] or "")
            if not revision_id:
                raise WorkLedgerError("work has no HEAD revision")
            return ledger.add_file_artifact(
                revision_id,
                logical_name=logical_name,
                path=path,
                provenance=provenance,
                verification_status="passed",
            )
        finally:
            ledger.close()

    def require_rework(
        self,
        binding: JobBinding,
        *,
        reason: str,
        gap_owner_repo: str = "",
        changed_contracts: Sequence[str] = (),
        verification_plan: Sequence[str] = (),
    ) -> dict[str, Any]:
        ledger = WorkLedger(self.path)
        try:
            work = ledger.get_work_by_code(binding.job_code)
            revision_id = str(work["head_revision_id"] or "")
            if not revision_id:
                raise WorkLedgerError("work has no HEAD revision")
            return ledger.request_rework(
                revision_id,
                reason=reason,
                gap_owner_repo=gap_owner_repo,
                changed_contracts=changed_contracts,
                verification_plan=verification_plan,
            )
        finally:
            ledger.close()

    def open_rework(
        self,
        binding: JobBinding,
        *,
        goal: str = "",
        plan: Mapping[str, Any] | None = None,
        reason: str = "",
        gap_owner_repo: str = "",
    ) -> dict[str, Any]:
        ledger = WorkLedger(self.path)
        try:
            work = ledger.get_work_by_code(binding.job_code)
            revision_id = str(work["head_revision_id"] or "")
            if not revision_id:
                raise WorkLedgerError("work has no HEAD revision")
            return ledger.open_rework(
                revision_id,
                goal=goal,
                plan=plan,
                reason=reason,
                gap_owner_repo=gap_owner_repo,
            )
        finally:
            ledger.close()


__all__ = ["WorkLedgerBridge"]
