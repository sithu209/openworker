from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker.runtimes.engineering_launch import packaged_process_config
from coworker.runtimes.harness import HarnessRuntimeError


def _assets(tmp_path: Path) -> None:
    root = tmp_path / "harness"
    (root / "upstream-plugin").mkdir(parents=True)
    (root / "upstream-lock.json").write_text(
        json.dumps({"commit": "47f943859bef60e4160492346772ded9b24f765a"}),
        encoding="utf-8",
    )
    (root / "upstream-plugin" / "openworker-engineering-tools.ts").write_text(
        "export {}\n", encoding="utf-8"
    )


def test_packaged_command_becomes_process_config(tmp_path: Path) -> None:
    _assets(tmp_path)
    workspace = tmp_path / "project"
    workspace.mkdir()
    env = {
        "OPENWORKER_RESOURCE_DIR": str(tmp_path),
        "OPENWORKER_HARNESS_COMMAND": json.dumps(["node.exe", "C:\\Program Files\\dsh\\server.mjs"]),
    }
    config = packaged_process_config(workspace, env)
    assert config is not None
    assert config.command == ("node.exe", "C:\\Program Files\\dsh\\server.mjs")
    assert config.cwd == workspace.resolve()


def test_missing_command_leaves_explicit_dev_fallback_available(tmp_path: Path) -> None:
    _assets(tmp_path)
    workspace = tmp_path / "project"
    workspace.mkdir()
    assert packaged_process_config(workspace, {"OPENWORKER_RESOURCE_DIR": str(tmp_path)}) is None


def test_configured_command_with_missing_assets_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    with pytest.raises(HarnessRuntimeError, match="configured packaged Harness is unavailable"):
        packaged_process_config(
            workspace,
            {"OPENWORKER_HARNESS_COMMAND": '["node","server.mjs"]', "OPENWORKER_RESOURCE_DIR": str(tmp_path)},
        )
