from __future__ import annotations

import json
from pathlib import Path

from coworker.runtimes.harness_packaging import harness_launch_capability, resolve_harness_layout


def _assets(tmp_path: Path) -> Path:
    root = tmp_path / "harness"
    (root / "upstream-plugin").mkdir(parents=True)
    (root / "upstream-lock.json").write_text(
        json.dumps({"commit": "47f943859bef60e4160492346772ded9b24f765a"}), encoding="utf-8"
    )
    (root / "upstream-plugin" / "openworker-engineering-tools.ts").write_text("export {}\n", encoding="utf-8")
    return root


def test_packaged_resource_root_resolves_harness_assets(tmp_path: Path) -> None:
    root = _assets(tmp_path)
    layout = resolve_harness_layout({"OPENWORKER_RESOURCE_DIR": str(tmp_path)})
    assert layout.root == root.resolve()
    assert layout.cordis_plugin.name == "openworker-engineering-tools.ts"


def test_assets_without_launch_command_are_not_runtime_capability(tmp_path: Path) -> None:
    _assets(tmp_path)
    capability = harness_launch_capability({"OPENWORKER_RESOURCE_DIR": str(tmp_path)})
    assert capability.available is False
    assert "not configured" in capability.reason


def test_windows_safe_json_command_is_supported(tmp_path: Path) -> None:
    _assets(tmp_path)
    capability = harness_launch_capability(
        {
            "OPENWORKER_RESOURCE_DIR": str(tmp_path),
            "OPENWORKER_HARNESS_COMMAND": json.dumps(["node.exe", "C:\\Program Files\\dsh\\server.mjs"]),
        }
    )
    assert capability.available is True
    assert capability.command == ("node.exe", "C:\\Program Files\\dsh\\server.mjs")


def test_missing_assets_fail_closed_even_when_command_is_set(tmp_path: Path) -> None:
    capability = harness_launch_capability(
        {
            "OPENWORKER_HARNESS_ASSET_DIR": str(tmp_path / "missing"),
            "OPENWORKER_RESOURCE_DIR": str(tmp_path / "also-missing"),
            "OPENWORKER_HARNESS_COMMAND": '["node","server.mjs"]',
        }
    )
    assert capability.available is False
    assert capability.layout is None
