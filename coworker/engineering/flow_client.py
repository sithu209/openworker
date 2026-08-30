"""Public AI-Engineering-OS managed-flow API.

Callers use this class instead of reaching into EngineeringOSClient private helpers.
The underlying workflow remains authoritative in AI-Engineering-OS.
"""
from __future__ import annotations

from typing import Any, Mapping

from .engineering_os import EngineeringOSClient, EngineeringOSContractError


class EngineeringOSFlowClient(EngineeringOSClient):
    """EngineeringOSClient with stable public workflow methods."""

    def execute_rc_column_flow(self, *, job_id: str, column: Mapping[str, Any]) -> dict[str, Any]:
        job_id = self._required_id(job_id, "job_id")
        if not isinstance(column, Mapping):
            raise TypeError("column must be a mapping")
        result = self._object(
            "POST",
            f"/api/v1/jobs/{job_id}/flows/rc-column",
            dict(column),
        )
        for field in ("job", "tasks", "stages", "artifacts"):
            if field not in result:
                raise EngineeringOSContractError(f"rc-column flow response missing {field}")
        return result
