from pathlib import Path

import pytest

from coworker.runtimes.engineering_scope import EngineeringScope
from coworker.runtimes.job_binding import JobBindingStore
from coworker.runtimes.project_knowledge import ProjectKnowledgeStore


def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectKnowledgeStore:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-ODAQN0D")
    JobBindingStore(tmp_path).create(
        EngineeringScope(
            project_id="p2",
            project_code="CASE-0002",
            job_id="j2",
            job_code="0002-ALADDIN",
        )
    )
    return ProjectKnowledgeStore(tmp_path)


def test_project_knowledge_rebuild_and_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path, monkeypatch)
    start = store.record(
        kind="dispatch",
        stage="shot-generation",
        status="running",
        summary="Harness started Case 0002",
        owner="OpenWorker",
        runtime="engineering-harness",
        session_id="acp-1",
        runtime_job_id="runtime-1",
        next_actions=("wait H3",),
        evidence=("run:1",),
    )
    store.record(
        kind="failure",
        stage="shot-generation",
        status="failed",
        summary="stale artifact rejected",
        blockers=("artifact provenance mismatch",),
        prompt_id="old-prompt",
        artifact_refs=("MiniMax_H3_00005_.mp4",),
        artifact_disposition="rejected",
    )
    accepted = store.record(
        kind="accepted",
        stage="shot-generation",
        status="running",
        summary="current prompt artifact accepted",
        prompt_id="new-prompt",
        execution_id="exec-2",
        artifact_refs=("MiniMax_H3_00006_.mp4",),
        artifact_disposition="accepted",
        next_actions=("generate remaining shots",),
    )
    snap = store.snapshot()
    assert snap.assigned_host == "DESKTOP-ODAQN0D"
    assert snap.latest_runtime_job_id == "runtime-1"
    assert snap.latest_session_id == "acp-1"
    assert snap.latest_prompt_id == "new-prompt"
    assert snap.blockers == ()
    assert snap.accepted_artifacts == ("MiniMax_H3_00006_.mp4",)
    assert snap.rejected_artifacts == ("MiniMax_H3_00005_.mp4",)
    assert start.event_id and accepted.event_id and start.event_id != accepted.event_id
    assert "new-prompt" in store.query("最新 prompt_id 是什麼？").answer
    assert "generate remaining shots" in store.query("下一步是什麼？").answer
    assert "runtime-1" in store.query("Harness runtime 到哪了？").answer


def test_ledger_is_append_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path, monkeypatch)
    store.record(kind="plan", stage="planning", summary="one")
    first = store.events_path.read_text(encoding="utf-8")
    store.record(kind="progress", stage="planning", summary="two")
    second = store.events_path.read_text(encoding="utf-8")
    assert second.startswith(first)
    assert store.snapshot().event_count == 2