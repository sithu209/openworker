from __future__ import annotations

import json
from pathlib import Path

import pytest

from coworker.runtimes.engineering_scope import EngineeringScope
from coworker.runtimes.job_binding import JobBindingStore
from coworker.runtimes.mission_guard import (
    DriftDecision,
    FailureGuidanceRequest,
    MissionAction,
    MissionDriftGuard,
    MissionGuardError,
    MissionStore,
)


def _binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMPUTERNAME", "DESKTOP-ODAQN0D")
    scope = EngineeringScope(
        project_id="project-0002",
        project_code="CASE-0002",
        job_id="job-0002",
        job_code="0002-ALADDIN",
    )
    return JobBindingStore(tmp_path).create(scope)


def _contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    binding = _binding(tmp_path, monkeypatch)
    return MissionStore(tmp_path).create_contract(
        mission_id="case-0002",
        user_goal="完成阿拉丁 source-to-film 正式交付",
        binding=binding,
        success_criteria=("final artifact has provenance", "delivery is published"),
        expected_deliverables=("segmented-videos", "final-video-1280x720"),
        allowed_capabilities=("engineering.source-to-film", "comfyx-studio.source-to-film"),
        owner_boundaries={
            "engineering.source-to-film": "AI-Engineering-OS",
            "comfyx-studio.source-to-film": "Comfyx-Studio",
        },
        prohibited_actions=("create second job", "migrate host"),
        authoritative_sources=("go-tool-runtime", "case docs"),
        max_retries_per_failure=2,
    )


def test_allows_action_inside_fixed_mission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    result = guard.assess(
        MissionAction(
            name="dispatch source-to-film",
            capability_id="engineering.source-to-film",
            owner="AI-Engineering-OS",
            project_id=contract.project_id,
            job_id=contract.job_id,
            assigned_host=contract.assigned_host,
            workspace_root=contract.workspace_root,
            side_effecting=True,
        )
    )

    assert result.decision is DriftDecision.ALLOW
    assert result.drift_score == 0


def test_blocks_host_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    result = guard.assess(
        MissionAction(
            name="resume production",
            capability_id="engineering.source-to-film",
            owner="AI-Engineering-OS",
            assigned_host="DESKTOP-O87",
            side_effecting=True,
        )
    )

    assert result.decision is DriftDecision.BLOCK
    assert any("host drift" in reason for reason in result.reasons)


def test_blocks_second_job_or_unknown_side_effect_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    second_job = guard.assess(MissionAction(name="create second job", side_effecting=True))
    unknown = guard.assess(
        MissionAction(name="direct studio delivery", capability_id="studio.direct-delivery", side_effecting=True)
    )

    assert second_job.decision is DriftDecision.BLOCK
    assert unknown.decision is DriftDecision.BLOCK
    assert any("outside mission allowlist" in reason for reason in unknown.reasons)


def test_blocks_owner_boundary_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    result = guard.assess(
        MissionAction(
            name="formal source-to-film",
            capability_id="engineering.source-to-film",
            owner="Comfyx-Studio",
            side_effecting=True,
        )
    )

    assert result.decision is DriftDecision.BLOCK
    assert any("owner boundary drift" in reason for reason in result.reasons)


def test_uncertainty_requeries_instead_of_guessing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    result = guard.assess(
        MissionAction(
            name="retry H3 with guessed dimensions",
            capability_id="engineering.source-to-film",
            owner="AI-Engineering-OS",
            uncertain=True,
            side_effecting=True,
        )
    )

    assert result.decision is DriftDecision.REQUERY
    assert result.should_requery is True


def test_retry_budget_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    result = guard.assess(
        MissionAction(
            name="retry source-to-film",
            capability_id="engineering.source-to-film",
            owner="AI-Engineering-OS",
            side_effecting=True,
            retry_key="h3.invalid-dimensions",
        ),
        retry_count=2,
    )

    assert result.decision is DriftDecision.BLOCK
    assert any("retry budget exhausted" in reason for reason in result.reasons)


def test_checkpoint_is_durable_and_monotonic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    store = MissionStore(tmp_path)

    first = store.checkpoint(
        contract,
        stage="planning",
        current_goal=contract.user_goal,
        current_owner="AI-Engineering-OS",
        current_capability="engineering.source-to-film",
        latest_evidence=("go-tool queried",),
        next_intended_action="dispatch",
    )
    second = store.checkpoint(
        contract,
        stage="generation",
        current_goal=contract.user_goal,
        latest_evidence=("prompt submitted",),
        retry_counts={"h3.timeout": 1},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert MissionStore(tmp_path).load_checkpoint() == second
    persisted = json.loads((tmp_path / ".openworker" / "mission-checkpoint.json").read_text(encoding="utf-8"))
    assert persisted["mission_id"] == "case-0002"


def test_contract_is_anchored_to_job_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    monkeypatch.setenv("COMPUTERNAME", "ANOTHER-HOST")

    with pytest.raises(Exception, match="assigned to host"):
        MissionDriftGuard(tmp_path, contract).assess(MissionAction(name="resume"))


def test_failure_requery_is_information_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract(tmp_path, monkeypatch)
    guard = MissionDriftGuard(tmp_path, contract)

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def query(self, workspace, question, *, project, session_id, task):
            self.calls.append((workspace, question, project, session_id, task))
            return "query-result"

    client = FakeClient()
    result = guard.requery_failure(
        client,  # type: ignore[arg-type]
        FailureGuidanceRequest(
            mission_id=contract.mission_id,
            stage="generation",
            failure_class="invalid-parameter",
            error="width and height must be positive multiples of 32",
            owner="ComfyX",
            capability_id="engineering.source-to-film",
            evidence=("current prompt failed",),
            parameters={"width": 1280, "height": 720},
        ),
        project="CASE-0002",
        session_id="session-1",
    )

    assert result == "query-result"
    assert len(client.calls) == 1
    _, question, project, session_id, task = client.calls[0]
    assert "multiples of 32" in question
    assert "Do not execute or mutate anything" in question
    assert project == "CASE-0002"
    assert session_id == "session-1"
    assert task == "mission drift/failure recovery planning"
