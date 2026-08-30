"""Model-facing one-call queue maintenance tool."""
from __future__ import annotations

from typing import Any

import aisuite as ai

from ..queue_drain import drain_queue


_SCHEMA = {
    "type": "function",
    "function": {
        "name": "queue_drain",
        "description": (
            "Immediately drain one registered go-tool-runtime capability queue. "
            "Use when a job is blocked by stale, duplicate, queued, waiting, or in-progress "
            "runs. One call owns query, cancel, retry, and verification and returns success "
            "only when clean=true and no active runs remain. Repeated calls are safe."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "capability_id": {
                    "type": "string",
                    "description": "Registered go-tool-runtime queue-admin capability id.",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Bounded total drain timeout. Default 120 seconds.",
                },
            },
            "required": ["capability_id"],
        },
    },
}


def queue_drain_tool():
    def queue_drain(capability_id: str, timeout_seconds: int = 120) -> dict[str, Any]:
        return drain_queue(capability_id, timeout_seconds=timeout_seconds)

    queue_drain.__name__ = "queue_drain"
    queue_drain.__doc__ = _SCHEMA["function"]["description"]
    # This is intentionally approval-free: the capability id is an allowlisted go-tool
    # administrative scope, and the user requires queue cleanup to be an immediate,
    # repeatable operational primitive. The underlying runtime remains fail-closed.
    queue_drain.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="queue_drain",
        category="operations",
        risk_level="low",
        capabilities=["queue_admin"],
        requires_approval=False,
    )
    queue_drain.__coworker_schema__ = _SCHEMA
    return queue_drain
