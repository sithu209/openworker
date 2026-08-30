"""Project lifecycle bridge for OpenWorker -> AI-Engineering-OS.

This module closes the bootstrap gap where OpenWorker could create Jobs but could
not create the authoritative OS Project that owns them. Business rules and ID
allocation remain in AI-Engineering-OS; OpenWorker only sends the typed request.
"""
from __future__ import annotations

from typing import Any, Mapping

from .engineering_os import EngineeringOSClient


class EngineeringOSProjectClient(EngineeringOSClient):
    """EngineeringOSClient with the missing Project create operation.

    Kept as a narrow extension so existing H11 behavior is unchanged while REAL
    autonomous cases can start from an empty OS database without a human-created
    Project prerequisite.
    """

    def create_project(
        self,
        *,
        code: str,
        name: str,
        description: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self._required_text(code, "code"),
            "name": self._required_text(name, "name"),
        }
        if description.strip():
            payload["description"] = description.strip()
        if metadata is not None:
            payload["metadata"] = dict(metadata)
        return self._object("POST", "/api/v1/projects", payload)

    def ensure_project(
        self,
        *,
        code: str,
        name: str,
        description: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return an existing matching Project or create it.

        Matching is deliberately fail-closed: only an exact Project code match is
        reused. Ambiguous duplicates are rejected instead of selecting one.
        """
        normalized_code = self._required_text(code, "code")
        matches = [
            project
            for project in self.list_projects()
            if str(project.get("code", "")).strip() == normalized_code
        ]
        if len(matches) > 1:
            raise RuntimeError(f"multiple AI-Engineering-OS projects use code {normalized_code!r}")
        if matches:
            return matches[0]
        return self.create_project(
            code=normalized_code,
            name=name,
            description=description,
            metadata=metadata,
        )
