"""H5 session ownership boundary for the DeepSeek Harness runtime.

OpenWorker owns durable product conversation identity.  The pinned Harness ACP
transport owns only fresh, connection-scoped runtime sessions and explicitly
cannot load/resume them after the sidecar is gone.  This module keeps that
limitation visible in code instead of inventing a second durable source of
truth or replaying historical user prompts (which could re-run tools).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HarnessSessionState(str, Enum):
    UNBOUND = "unbound"
    LIVE = "live"
    LOST = "lost"


class HarnessSessionResumeUnsupported(RuntimeError):
    """Raised when durable Harness resume is requested through ACP rc.5."""


@dataclass(frozen=True)
class HarnessSessionBinding:
    """Maps one durable OpenWorker conversation to one ephemeral ACP session."""

    conversation_id: str
    acp_session_id: str | None = None
    state: HarnessSessionState = HarnessSessionState.UNBOUND

    @property
    def live(self) -> bool:
        return self.state is HarnessSessionState.LIVE and bool(self.acp_session_id)


class HarnessSessionCoordinator:
    """Own process-local ACP bindings without pretending they are durable.

    Durable transcript, title, grants, compaction state and product metadata stay
    in ConversationStore.  ACP session ids are deliberately *not* persisted:
    upstream documents them as connection-owned and fresh-session-only.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, HarnessSessionBinding] = {}

    def binding(self, conversation_id: str) -> HarnessSessionBinding:
        if not conversation_id:
            raise ValueError("conversation_id must not be empty")
        return self._bindings.get(
            conversation_id,
            HarnessSessionBinding(conversation_id=conversation_id),
        )

    def bind_live(self, conversation_id: str, acp_session_id: str) -> HarnessSessionBinding:
        if not conversation_id:
            raise ValueError("conversation_id must not be empty")
        if not acp_session_id:
            raise ValueError("acp_session_id must not be empty")
        current = self._bindings.get(conversation_id)
        if current is not None and current.live and current.acp_session_id != acp_session_id:
            raise RuntimeError("conversation already has a different live ACP session")
        binding = HarnessSessionBinding(
            conversation_id=conversation_id,
            acp_session_id=acp_session_id,
            state=HarnessSessionState.LIVE,
        )
        self._bindings[conversation_id] = binding
        return binding

    def mark_connection_lost(self) -> None:
        """Invalidate every ACP id when its owning stdio connection disappears."""
        for conversation_id, binding in tuple(self._bindings.items()):
            if binding.live:
                self._bindings[conversation_id] = HarnessSessionBinding(
                    conversation_id=conversation_id,
                    acp_session_id=None,
                    state=HarnessSessionState.LOST,
                )

    def discard(self, conversation_id: str) -> None:
        self._bindings.pop(conversation_id, None)

    def require_durable_resume(self, conversation_id: str) -> None:
        """Fail closed rather than replaying old prompts and re-running side effects."""
        binding = self.binding(conversation_id)
        raise HarnessSessionResumeUnsupported(
            "pinned DeepSeek Harness ACP supports fresh sessions only; "
            f"durable resume is unavailable for OpenWorker conversation {binding.conversation_id!r}. "
            "Do not replay historical user prompts as a substitute because that can repeat tool side effects."
        )

    def capabilities(self) -> dict[str, bool]:
        return {
            "fresh_session": True,
            "same_connection_multi_turn": True,
            "durable_resume": False,
            "session_load": False,
            "session_list": False,
            "session_delete": False,
            "session_fork": False,
            "transcript_replay": False,
        }
