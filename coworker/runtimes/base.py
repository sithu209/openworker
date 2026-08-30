"""Agent runtime contract for OpenWorker.

H1 introduces a small structural seam while the existing TurnEngine remains
the only active runtime and keeps all current behaviour.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional, Protocol

from ..events import Event


class AgentRuntime(Protocol):
    """Lifecycle surface shared by OpenWorker agent runtimes."""

    def run(
        self,
        user_input: str | list,
        *,
        source: Optional[dict[str, Any]] = None,
        display: Optional[str] = None,
    ) -> AsyncIterator[Event]: ...

    def retry(self) -> AsyncIterator[Event]: ...

    def resume(self) -> AsyncIterator[Event]: ...

    def request_interrupt(self) -> None: ...

    def queue_steering(
        self, text: str, source: Optional[dict[str, Any]] = None
    ) -> None: ...

    def switch_model(self, model: str) -> Optional[str]: ...
