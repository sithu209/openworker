from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker.runtimes.manager import DEFAULT_RUNTIME, RuntimeKind, RuntimeUnavailableError, select_runtime


def _assets(tmp_path: Path) -> None:
    root = tmp_path / "harness"
    (root / "upstream-plugin").mkdir(parents=True)
    (root / "upstream-lock.json").write_text(
        json.dumps({"commit": "47f943859bef60e4160492346772ded9b24f765a"}), encoding="utf-8"
    )
    (root / "upstream-plugin" / "openworker-engineering-tools.ts").write_text("export {}\n", encoding="utf-8")


def test_h11_native_remains_default() -> None:
    assert DEFAULT_RUNTIME is RuntimeKind.NATIVE
    assert select_runtime(None, env={}) is RuntimeKind.NATIVE


def test_harness_cannot_be_selected_accidentally() -> None:
    with pytest.raises(RuntimeUnavailableError, match="opt-in"):
        select_runtime("harness", env={})


def test_harness_opt_in_still_requires_launch_capability(tmp_path: Path) -> None:
    _assets(tmp_path)
    with pytest.raises(RuntimeUnavailableError, match="not configured"):
        select_runtime(
            "harness",
            env={"OPENWORKER_HARNESS_ENABLED": "1", "OPENWORKER_RESOURCE_DIR": str(tmp_path)},
        )


def test_harness_can_be_explicitly_selected_when_packaging_gate_is_ready(tmp_path: Path) -> None:
    _assets(tmp_path)
    selected = select_runtime(
        "harness",
        env={
            "OPENWORKER_HARNESS_ENABLED": "1",
            "OPENWORKER_RESOURCE_DIR": str(tmp_path),
            "OPENWORKER_HARNESS_COMMAND": '["node","server.mjs"]',
        },
    )
    assert selected is RuntimeKind.HARNESS
