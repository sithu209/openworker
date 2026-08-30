"""Runtime selection primitives and H11 default-runtime policy."""

from __future__ import annotations

import os
from enum import Enum
from typing import Mapping, Optional

from .harness_packaging import harness_launch_capability


class RuntimeKind(str, Enum):
    NATIVE = "native"
    HARNESS = "harness"


# H11 decision: Native remains the product default until real same-machine H8
# RC A/B and H9 GPU/MP4 evidence justify promotion. Harness is explicit opt-in.
DEFAULT_RUNTIME = RuntimeKind.NATIVE


class RuntimeUnavailableError(ValueError):
    """Raised when a known runtime is requested but its deployment is unavailable."""


def parse_runtime(value: Optional[str]) -> RuntimeKind:
    if value is None or not str(value).strip():
        return DEFAULT_RUNTIME
    try:
        return RuntimeKind(str(value).strip().lower())
    except ValueError as exc:
        choices = ", ".join(item.value for item in RuntimeKind)
        raise ValueError(f"unknown agent runtime {value!r}; expected one of: {choices}") from exc


def require_available(
    kind: RuntimeKind,
    *,
    env: Mapping[str, str] | None = None,
) -> RuntimeKind:
    if kind is RuntimeKind.NATIVE:
        return kind
    env = os.environ if env is None else env
    enabled = str(env.get("OPENWORKER_HARNESS_ENABLED", "")).strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        raise RuntimeUnavailableError(
            "agent runtime 'harness' is opt-in; set OPENWORKER_HARNESS_ENABLED=1 explicitly"
        )
    capability = harness_launch_capability(env)
    if not capability.available:
        raise RuntimeUnavailableError(
            f"agent runtime 'harness' is unavailable: {capability.reason}"
        )
    return kind


def select_runtime(
    value: Optional[str] = None,
    *,
    env: Mapping[str, str] | None = None,
) -> RuntimeKind:
    """Resolve runtime; missing remains Native, Harness requires explicit healthy deployment."""
    return require_available(parse_runtime(value), env=env)


__all__ = [
    "DEFAULT_RUNTIME",
    "RuntimeKind",
    "RuntimeUnavailableError",
    "parse_runtime",
    "require_available",
    "select_runtime",
]
