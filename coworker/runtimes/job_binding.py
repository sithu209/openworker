"""Persistent OpenWorker binding for one job to one machine and workspace.

A job is assigned once, at creation. Subsequent OpenWorker resumes must use the
same host and workspace unless an explicit migration mechanism is introduced.
This keeps local models, ComfyUI state, paths, evidence and delivery ownership
stable across multiple Action invocations for the same job.

Creating a fixed binding also bootstraps the Job's Git-like WorkLedger. This is a
platform invariant: every real OpenWorker job has durable revision/rework history
from the moment it is created, rather than relying on individual cases to opt in.
Loading/resuming a binding also replays any unsynced ProjectKnowledge events into
the ledger, so crashes cannot leave work progress permanently outside history.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path

from .engineering_scope import EngineeringScope


class JobBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobBinding:
    schema_version: str
    assigned_host: str
    workspace_root: str
    project_id: str
    project_code: str
    job_id: str
    job_code: str

    def scope(self) -> EngineeringScope:
        return EngineeringScope(
            project_id=self.project_id,
            project_code=self.project_code,
            job_id=self.job_id,
            job_code=self.job_code,
        )


class JobBindingStore:
    def __init__(self, workspace: str | os.PathLike[str]) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.path = self.workspace / ".openworker" / "job-binding.json"

    @staticmethod
    def current_host() -> str:
        for value in (os.environ.get("COMPUTERNAME"), os.environ.get("HOSTNAME")):
            normalized = str(value or "").strip()
            if normalized:
                return normalized
        try:
            return str(socket.gethostname() or "").strip()
        except OSError:
            return ""

    def load(self) -> JobBinding | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise JobBindingError(f"invalid OpenWorker job binding: {exc}") from exc
        try:
            binding = JobBinding(**raw)
        except TypeError as exc:
            raise JobBindingError(f"unsupported OpenWorker job binding schema: {exc}") from exc
        self.assert_current(binding)

        from .work_ledger_bridge import WorkLedgerBridge

        try:
            bridge = WorkLedgerBridge(self.workspace)
            bridge.ensure(binding)
            bridge.sync_pending_project_events(binding)
        except Exception as exc:
            raise JobBindingError(f"cannot synchronize mandatory work ledger: {exc}") from exc
        return binding

    def assert_current(self, binding: JobBinding) -> None:
        expected_workspace = os.path.normcase(str(self.workspace))
        actual_workspace = os.path.normcase(str(Path(binding.workspace_root).expanduser().resolve()))
        if actual_workspace != expected_workspace:
            raise JobBindingError(
                f"job workspace is fixed to {binding.workspace_root}; current workspace is {self.workspace}"
            )
        host = self.current_host()
        if not host:
            raise JobBindingError("cannot determine current host for fixed-host job")
        if binding.assigned_host.casefold() != host.casefold():
            raise JobBindingError(
                f"job is assigned to host {binding.assigned_host}; current host is {host}. "
                "Explicit migration is required before another host may resume it."
            )

    def create(self, scope: EngineeringScope) -> JobBinding:
        if self.path.exists():
            raise JobBindingError(f"job binding already exists: {self.path}")
        host = self.current_host()
        if not host:
            raise JobBindingError("cannot determine current host for fixed-host job")
        binding = JobBinding(
            schema_version="openworker.job-binding.v1",
            assigned_host=host,
            workspace_root=str(self.workspace),
            project_id=scope.project_id,
            project_code=scope.project_code,
            job_id=scope.job_id,
            job_code=scope.job_code,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(binding), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

        from .work_ledger_bridge import WorkLedgerBridge

        try:
            WorkLedgerBridge(self.workspace).ensure(binding)
        except Exception as exc:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
            raise JobBindingError(f"cannot bootstrap mandatory work ledger: {exc}") from exc
        return binding


__all__ = ["JobBinding", "JobBindingError", "JobBindingStore"]
