from __future__ import annotations

from pathlib import Path

import pytest

from coworker.runtimes.engineering_scope import EngineeringScope
from coworker.runtimes.job_binding import JobBindingStore
from coworker.runtimes.project_knowledge import ProjectKnowledgeStore


def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectKnowledgeStore:
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-ODAQN0D")
    JobBindingStore(tmp_path).create(
        EngineeringScope(
            project_id="prj-2",
            project_code="CASE-0002",
            job_id="job-2",
            job_code="0002-ALADDIN",
        )
    )
    return ProjectKnowledgeStore(tmp_path)


def test_answers_project_progress_from_durable_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path, monkeypatch)
    store.record(
        kind="progress",
        stage="source-to-film",
        status="running",
        summary="Studio production queue 已提交 H3 shot-1",
        owner="Comfyx-Studio",
        capability_id="comfyx-studio.source-to-film",
        evidence=("prompt_id=abc",),
        next_actions=("等待 exact prompt terminal",),
    )
    store.record(
        kind="result",
        stage="source-to-film",
        status="succeeded",
        summary="shot-1 已由 exact prompt 產生非空 MP4",
        evidence=("prompt_id=abc", "MiniMax_H3_00006_.mp4"),
        next_actions=("做內容 QC", "進入下一段生成"),
    )

    answer = store.query("這個項目做到哪了？")

    assert "CASE-0002" in answer.answer
    assert "succeeded" in answer.answer
    assert "shot-1" in answer.answer
    assert "內容 QC" in answer.answer
    assert answer.snapshot.event_count == 2


def test_answers_blockers_and_next_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path, monkeypatch)
    store.record(
        kind="failure",
        stage="generation",
        status="blocked",
        summary="H3 參數驗證失敗",
        blockers=("720 不是 32 的倍數",),
        decisions=("生成改用 1280x736",),
        next_actions=("原生畫布生成後 center crop 到 1280x720",),
    )

    blockers = store.query("目前卡在哪？")
    next_step = store.query("下一步是什麼？")

    assert "720 不是 32 的倍數" in blockers.answer
    assert "1280x720" in next_step.answer


def test_detail_question_returns_relevant_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path, monkeypatch)
    store.record(kind="decision", stage="routing", summary="固定由 ODAQ 執行 production", details={"host": "DESKTOP-ODAQN0D"})
    store.record(kind="result", stage="generation", summary="H3 shot-1 完成", evidence=("prompt_id=xyz",))

    answer = store.query("H3 的 prompt_id 是什麼？")

    assert "prompt_id=xyz" in str(answer.matched_events[0].evidence)
    assert "H3 shot-1 完成" in answer.answer


def test_journal_is_append_only_across_store_instances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path, monkeypatch)
    first = store.record(kind="progress", stage="a", summary="第一批")
    second = ProjectKnowledgeStore(tmp_path).record(kind="progress", stage="b", summary="第二批")

    snapshot = ProjectKnowledgeStore(tmp_path).snapshot()
    assert first.sequence == 1
    assert second.sequence == 2
    assert snapshot.event_count == 2
    assert snapshot.latest_summary == "第二批"
