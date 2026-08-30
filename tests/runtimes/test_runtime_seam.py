from __future__ import annotations

import pytest

from coworker.agent import build_engine
from coworker.agents import chat_agent
from coworker.engine import TurnEngine
from coworker.events import Event, EventType
from coworker.providers import ModelCapabilities, ProviderClient
from coworker.runtimes import (
    AgentRuntime,
    NativeRuntime,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeKind,
    RuntimeUnavailableError,
    select_runtime,
)


class _NoopProvider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        raise AssertionError("runtime construction must not call the model")

    def capabilities(self, model):
        return ModelCapabilities()


def test_native_runtime_preserves_turn_engine_contract() -> None:
    assert issubclass(NativeRuntime, TurnEngine)
    for method in (
        "run",
        "retry",
        "resume",
        "request_interrupt",
        "queue_steering",
        "switch_model",
    ):
        assert hasattr(NativeRuntime, method)
        assert hasattr(AgentRuntime, method)


def test_build_engine_constructs_native_runtime() -> None:
    engine = build_engine(agent=chat_agent(), provider=_NoopProvider())
    assert isinstance(engine, NativeRuntime)


def test_runtime_events_reuse_existing_openworker_contract() -> None:
    assert RuntimeEvent is Event
    assert RuntimeEventType is EventType


def test_runtime_selection_defaults_to_native() -> None:
    assert select_runtime() is RuntimeKind.NATIVE
    assert select_runtime("") is RuntimeKind.NATIVE
    assert select_runtime(" NATIVE ") is RuntimeKind.NATIVE


def test_harness_is_fail_closed_until_implemented() -> None:
    with pytest.raises(RuntimeUnavailableError, match="harness"):
        select_runtime("harness")


def test_unknown_runtime_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown agent runtime"):
        select_runtime("not-a-runtime")
