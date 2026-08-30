from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _manifest(workspace: Path) -> dict:
    return {
        "schema_version": "openworker-case-worklist/v1",
        "case_id": "x",
        "workspace_root": str(workspace.resolve()),
        "assigned_host": "HOST",
        "revision": 1,
        "steps": [
            {
                "step_id": "x-010",
                "title": "first",
                "kind": "work",
                "dependencies": [],
                "allowed_actions": ["do.first"],
                "acceptance": [],
                "status": "PENDING",
                "evidence": {},
                "blocker": "",
                "repair_parent_step": "",
                "allow_skip": False,
            }
        ],
    }


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/case_worklist_action.py", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def test_block_active_blocks_running_and_is_idempotent(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest(workspace)), encoding="utf-8")

    assert _run(repo, "ensure", "--workspace-root", str(workspace), "--manifest", str(manifest)).returncode == 0
    assert _run(
        repo,
        "start",
        "--workspace-root",
        str(workspace),
        "--step-id",
        "x-010",
        "--action-id",
        "do.first",
        "--execution-id",
        "test-exec-1",
    ).returncode == 0

    first = _run(
        repo,
        "block-active",
        "--workspace-root",
        str(workspace),
        "--step-id",
        "x-010",
        "--reason",
        "workflow failed",
    )
    assert first.returncode == 0

    second = _run(
        repo,
        "block-active",
        "--workspace-root",
        str(workspace),
        "--step-id",
        "x-010",
        "--reason",
        "workflow failed again",
    )
    assert second.returncode == 0

    state = json.loads((workspace / ".openworker" / "case-worklist.json").read_text(encoding="utf-8"))
    assert state["steps"][0]["status"] == "BLOCKED"
    assert state["steps"][0]["blocker"] == "workflow failed"
    assert "__openworker_active_action" not in state["steps"][0]["evidence"]
