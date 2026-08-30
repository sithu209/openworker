"""AI-Engineering-OS Project/Job scope acquisition for one-command engineering runs."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx


class EngineeringScopeError(RuntimeError):
    """Raised when a Project/Job scope cannot be established safely."""


@dataclass(frozen=True)
class EngineeringScope:
    project_id: str
    project_code: str
    job_id: str
    job_code: str


def workspace_project_code(workspace: str | os.PathLike[str]) -> str:
    root = Path(workspace).expanduser().resolve()
    canonical = os.path.normcase(str(root)).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:12].upper()
    return f"OW-{digest}"


class EngineeringOSScopeClient:
    """Thin client over the existing project/job management API.

    Project identity is deterministic for a workspace path so repeated OpenWorker
    launches reuse the same AI-Engineering-OS project. Every run creates a fresh
    job so artifacts and lineage from unrelated requests never get merged.
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout_s: float = 30.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            raise ValueError("Engineering-OS base_url is required")
        self.base_url = base
        self.token = str(token or "").strip()
        self._owns_client = client is None
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.client = client or httpx.Client(timeout=timeout_s, headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, f"{self.base_url}{path}", **kwargs)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EngineeringScopeError(f"Engineering-OS scope request failed: {exc}") from exc
        if response.is_error:
            raise EngineeringScopeError(
                f"Engineering-OS scope request {method} {path} failed ({response.status_code}): {payload}"
            )
        if not isinstance(payload, dict):
            raise EngineeringScopeError("Engineering-OS scope response must be a JSON object")
        return payload

    def ensure(self, workspace: str | os.PathLike[str], user_request: str) -> EngineeringScope:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            raise EngineeringScopeError(f"Project Workspace does not exist: {root}")
        request = str(user_request or "").strip()
        if not request:
            raise EngineeringScopeError("user_request must not be empty")
        code = workspace_project_code(root)
        project = self._find_project(code)
        if project is None:
            project = self._json(
                "POST",
                "/api/v1/projects",
                json={
                    "code": code,
                    "name": root.name or code,
                    "description": "OpenWorker Project Workspace",
                    "metadata": {"workspace_root": str(root), "managed_by": "openworker"},
                },
            )
        project_id = self._required_string(project, "id", "project")
        project_code = self._required_string(project, "code", "project")
        job_code = self._new_job_code()
        job = self._json(
            "POST",
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "code": job_code,
                "name": f"{root.name or 'Workspace'} OpenWorker run",
                "user_request": request,
                "priority": "normal",
                "metadata": {"workspace_root": str(root), "managed_by": "openworker"},
            },
        )
        return EngineeringScope(
            project_id=project_id,
            project_code=project_code,
            job_id=self._required_string(job, "id", "job"),
            job_code=self._required_string(job, "code", "job"),
        )

    def _find_project(self, code: str) -> dict[str, Any] | None:
        payload = self._json("GET", "/api/v1/projects")
        items = payload.get("items")
        if not isinstance(items, list):
            raise EngineeringScopeError("Engineering-OS project list has no items array")
        matches = [
            item for item in items
            if isinstance(item, dict) and str(item.get("code") or "").strip().casefold() == code.casefold()
        ]
        if len(matches) > 1:
            raise EngineeringScopeError(f"ambiguous Engineering-OS project code: {code}")
        return matches[0] if matches else None

    @staticmethod
    def _new_job_code() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"OWJ-{stamp}-{secrets.token_hex(3).upper()}"

    @staticmethod
    def _required_string(payload: dict[str, Any], field: str, kind: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise EngineeringScopeError(f"Engineering-OS {kind} response has no {field}")
        return value.strip()


__all__ = [
    "EngineeringOSScopeClient",
    "EngineeringScope",
    "EngineeringScopeError",
    "workspace_project_code",
]
