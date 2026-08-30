"""OpenWorker helpers for the OS-owned source-to-film lifecycle.

The agent talks only to AI-Engineering-OS. OS remains responsible for the
Comfyx-Studio adapter and provenance; this module never calls Studio directly.
"""
from __future__ import annotations

import time
from typing import Any

from .engineering_os import EngineeringOSContractError
from .project_lifecycle import EngineeringOSProjectClient


class EngineeringOSMediaClient(EngineeringOSProjectClient):
    def source_to_film_status(self, *, job_id: str) -> dict[str, Any]:
        job_id = self._required_id(job_id, "job_id")
        result = self._object("GET", f"/api/v1/jobs/{job_id}/flows/source-to-film/status")
        if result.get("os_job_id") != job_id:
            raise EngineeringOSContractError("source-to-film status os_job_id does not match requested job")
        queue_id = result.get("queue_id")
        queue = result.get("queue")
        if not isinstance(queue_id, str) or not queue_id.strip():
            raise EngineeringOSContractError("source-to-film status missing queue_id")
        if not isinstance(queue, dict):
            raise EngineeringOSContractError("source-to-film status missing queue object")
        if not isinstance(queue.get("status"), str) or not queue["status"].strip():
            raise EngineeringOSContractError("source-to-film status queue missing status")
        return result

    @staticmethod
    def _validate_success_queue(result: dict[str, Any]) -> None:
        """Fail closed unless a succeeded film queue contains real shot artifacts."""
        queue = result.get("queue")
        if not isinstance(queue, dict):
            raise EngineeringOSContractError("source-to-film success missing queue object")
        items = queue.get("items")
        if not isinstance(items, list):
            raise EngineeringOSContractError("source-to-film succeeded without queue items")
        shots = [item for item in items if isinstance(item, dict) and item.get("kind") == "shot.generate"]
        if not shots:
            raise EngineeringOSContractError("source-to-film succeeded without shot.generate items")
        for item in shots:
            item_id = str(item.get("id", "")).strip() or "<unknown>"
            if str(item.get("status", "")).strip().lower() != "succeeded":
                raise EngineeringOSContractError(
                    f"source-to-film success contains non-succeeded shot item: {item_id}"
                )
            output = item.get("output")
            if not isinstance(output, dict):
                raise EngineeringOSContractError(
                    f"source-to-film succeeded shot has no output: {item_id}"
                )
            artifacts = output.get("artifacts")
            if not isinstance(artifacts, list) or not any(
                isinstance(value, str) and value.strip() for value in artifacts
            ):
                raise EngineeringOSContractError(
                    f"source-to-film succeeded shot has no artifact: {item_id}"
                )

    def wait_source_to_film(self, *, job_id: str, timeout_seconds: float = 1800,
                            poll_seconds: float = 5) -> dict[str, Any]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be > 0")
        deadline = time.monotonic() + timeout_seconds
        while True:
            result = self.source_to_film_status(job_id=job_id)
            status = str(result["queue"]["status"]).strip().lower()
            if status in {"succeeded", "failed", "cancelled", "canceled"}:
                if status == "succeeded":
                    self._validate_success_queue(result)
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError(f"source-to-film timed out for OS job {job_id}")
            time.sleep(poll_seconds)
