"""Launch adapter for the one-command engineering Host.

H10 owns packaged Harness asset/command discovery. This module only converts that
existing capability contract into the H3 HarnessProcessConfig used by the Host.
It never scans arbitrary paths or invents an executable location.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .harness import HarnessProcessConfig, HarnessRuntimeError
from .harness_packaging import harness_launch_capability


def packaged_process_config(
    workspace: str | os.PathLike[str],
    env: Mapping[str, str] | None = None,
) -> HarnessProcessConfig | None:
    """Return the configured packaged Harness process, or None for dev fallback.

    A missing OPENWORKER_HARNESS_COMMAND means the caller may use the explicit
    pinned-source development fallback. A configured but invalid packaged launch
    fails closed instead of silently switching to another runtime.
    """
    env = os.environ if env is None else env
    raw_command = str(env.get("OPENWORKER_HARNESS_COMMAND", "")).strip()
    capability = harness_launch_capability(env)
    if capability.available:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            raise HarnessRuntimeError(f"Project Workspace does not exist: {root}")
        return HarnessProcessConfig(
            command=capability.command,
            cwd=root,
            env={},
            startup_timeout_s=30.0,
            request_timeout_s=300.0,
        )
    if raw_command:
        raise HarnessRuntimeError(
            f"configured packaged Harness is unavailable: {capability.reason}"
        )
    return None


__all__ = ["packaged_process_config"]
