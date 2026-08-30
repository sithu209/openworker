from __future__ import annotations

import pytest

from coworker.runtimes.harness_sessions import (
    HarnessSessionCoordinator,
    HarnessSessionResumeUnsupported,
    HarnessSessionState,
)


def test_unbound_product_conversation_is_not_a_fake_acp_session() -> None:
    coordinator = HarnessSessionCoordinator()
    binding = coordinator.binding("conv-1")
    assert binding.conversation_id == "conv-1"
    assert binding.acp_session_id is None
    assert binding.state is HarnessSessionState.UNBOUND
    assert binding.live is False


def test_live_binding_is_process_local_and_stable() -> None:
    coordinator = HarnessSessionCoordinator()
    binding = coordinator.bind_live("conv-1", "acp-1")
    assert binding.live is True
    assert coordinator.binding("conv-1") == binding
    assert coordinator.bind_live("conv-1", "acp-1") == binding


def test_conflicting_live_session_id_is_rejected() -> None:
    coordinator = HarnessSessionCoordinator()
    coordinator.bind_live("conv-1", "acp-1")
    with pytest.raises(RuntimeError, match="different live ACP session"):
        coordinator.bind_live("conv-1", "acp-2")


def test_connection_loss_invalidates_acp_ids_without_deleting_product_identity() -> None:
    coordinator = HarnessSessionCoordinator()
    coordinator.bind_live("conv-1", "acp-1")
    coordinator.bind_live("conv-2", "acp-2")
    coordinator.mark_connection_lost()
    for conversation_id in ("conv-1", "conv-2"):
        binding = coordinator.binding(conversation_id)
        assert binding.conversation_id == conversation_id
        assert binding.acp_session_id is None
        assert binding.state is HarnessSessionState.LOST
        assert binding.live is False


def test_durable_resume_fails_closed_instead_of_replaying_history() -> None:
    coordinator = HarnessSessionCoordinator()
    coordinator.bind_live("conv-1", "acp-1")
    coordinator.mark_connection_lost()
    with pytest.raises(HarnessSessionResumeUnsupported, match="Do not replay historical user prompts"):
        coordinator.require_durable_resume("conv-1")


def test_capabilities_report_upstream_fresh_session_limit() -> None:
    caps = HarnessSessionCoordinator().capabilities()
    assert caps["fresh_session"] is True
    assert caps["same_connection_multi_turn"] is True
    assert caps["durable_resume"] is False
    assert caps["session_load"] is False
    assert caps["transcript_replay"] is False
