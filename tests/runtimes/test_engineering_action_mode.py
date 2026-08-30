from __future__ import annotations

import asyncio

import pytest

from coworker.engine import ApprovalOutcome, PermissionRequest
from coworker.engineering_cli import _action_approver, main


def _request(name: str) -> PermissionRequest:
    return PermissionRequest(tool_name=name, arguments={}, metadata=None, reason="test")


def test_action_approver_allows_only_exact_tool_names() -> None:
    approve = _action_approver({"engineering__source_to_film", "engineering__job_status"})
    assert asyncio.run(approve(_request("engineering__source_to_film"))) is ApprovalOutcome.ONCE
    assert asyncio.run(approve(_request("engineering__job_status"))) is ApprovalOutcome.ONCE
    assert asyncio.run(approve(_request("shell"))) is ApprovalOutcome.DENY
    assert asyncio.run(approve(_request("engineering__source_to_film_extra"))) is ApprovalOutcome.DENY


def test_action_mode_requires_explicit_allowlist(tmp_path) -> None:
    (tmp_path / "TASK.md").write_text("Do work", encoding="utf-8")
    with pytest.raises(SystemExit, match="requires at least one exact --allow-tool"):
        main(["--workspace", str(tmp_path), "--action-mode"])


def test_action_mode_rejects_unrestricted_auto_approve(tmp_path) -> None:
    (tmp_path / "TASK.md").write_text("Do work", encoding="utf-8")
    with pytest.raises(SystemExit, match="cannot be combined"):
        main([
            "--workspace", str(tmp_path),
            "--action-mode",
            "--auto-approve",
            "--allow-tool", "engineering__source_to_film",
        ])