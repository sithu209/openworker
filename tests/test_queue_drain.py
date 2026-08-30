from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker import queue_drain


def _runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "gtr"
    (root / "cmd" / "gtr-actions-queue").mkdir(parents=True)
    (root / "config.yaml").write_text("actions:\n  enabled: true\n", encoding="utf-8")
    return root


def test_queue_drain_returns_immediately_when_clean(monkeypatch, tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)

    class Proc:
        returncode = 0
        stdout = json.dumps({"clean": True, "cancelled": [], "preserved": [], "still_active": [], "errors": []})
        stderr = ""

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Proc()

    monkeypatch.setattr(queue_drain.subprocess, "run", fake_run)
    result = queue_drain.drain_queue("presentation.openmaic", runtime_root=str(root))

    assert result["clean"] is True
    assert result["remaining_active"] == []
    assert result["attempt_count"] == 1
    assert "--cancel-active=true" in calls[0][0]
    assert "--workflow-scoped=true" in calls[0][0]


def test_queue_drain_retries_inside_one_call_until_clean(monkeypatch, tmp_path: Path) -> None:
    root = _runtime_root(tmp_path)
    reports = iter(
        [
            {"clean": False, "cancelled": [101], "still_active": [101], "errors": []},
            {"clean": True, "cancelled": [], "preserved": [], "still_active": [], "errors": []},
        ]
    )

    class Proc:
        returncode = 0
        stderr = ""
        def __init__(self, payload):
            self.stdout = json.dumps(payload)

    monkeypatch.setattr(queue_drain.subprocess, "run", lambda *a, **k: Proc(next(reports)))
    monkeypatch.setattr(queue_drain.time, "sleep", lambda *_: None)

    result = queue_drain.drain_queue(
        "presentation.openmaic",
        runtime_root=str(root),
        timeout_seconds=10,
        retry_interval_seconds=0,
    )
    assert result["clean"] is True
    assert result["attempt_count"] == 2


def test_queue_drain_fails_closed_without_capability() -> None:
    with pytest.raises(queue_drain.QueueDrainError, match="capability_id is required"):
        queue_drain.drain_queue("   ")
