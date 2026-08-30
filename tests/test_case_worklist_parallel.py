from pathlib import Path

import pytest

from coworker.case_worklist import CaseStep, CaseWorklist, CaseWorklistError, StepStatus
from coworker.case_worklist_runtime import CaseWorklistRuntime


def make_worklist(tmp_path: Path) -> CaseWorklist:
    return CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[
            CaseStep("010", "root", allowed_actions=["a.root"], acceptance=["ok"]),
            CaseStep("030", "characters", dependencies=["010"], allowed_actions=["a.image"], acceptance=["ok"]),
            CaseStep("040", "scenes", dependencies=["010"], allowed_actions=["a.image"], acceptance=["ok"]),
            CaseStep("050", "join", dependencies=["030", "040"], allowed_actions=["a.join"], acceptance=["ok"]),
        ],
        parallel_policy={
            "authority": "openworker-local-supervisor",
            "max_local_slots": 4,
            "fanout_join": [{"parallel_steps": ["030", "040"], "join_step": "050"}],
        },
    )


def pass_with_evidence(worklist: CaseWorklist, step_id: str, action: str) -> None:
    worklist.start(step_id, action)
    worklist.record_evidence(step_id, "ok", True)
    worklist.pass_step(step_id)


def test_parallel_frontier_allows_two_independent_running_steps(tmp_path: Path) -> None:
    worklist = make_worklist(tmp_path)
    pass_with_evidence(worklist, "010", "a.root")
    assert [step.step_id for step in worklist.ready_steps()] == ["030", "040"]

    worklist.start("030", "a.image")
    worklist.start("040", "a.image")
    assert [step.step_id for step in worklist.running_steps()] == ["030", "040"]


def test_join_waits_for_both_parallel_parents(tmp_path: Path) -> None:
    worklist = make_worklist(tmp_path)
    pass_with_evidence(worklist, "010", "a.root")
    pass_with_evidence(worklist, "030", "a.image")
    assert [step.step_id for step in worklist.ready_steps()] == ["040"]
    pass_with_evidence(worklist, "040", "a.image")
    assert [step.step_id for step in worklist.ready_steps()] == ["050"]


def test_legacy_next_step_remains_compatible_with_parallel_running(tmp_path: Path) -> None:
    worklist = make_worklist(tmp_path)
    pass_with_evidence(worklist, "010", "a.root")
    worklist.start("030", "a.image")
    worklist.start("040", "a.image")
    assert worklist.next_step().step_id == "030"
    payload = worklist.as_dict()
    assert payload["running_step_ids"] == ["030", "040"]


def test_parallel_policy_survives_round_trip(tmp_path: Path) -> None:
    original = make_worklist(tmp_path)
    payload = original.as_dict()
    restored = CaseWorklist.from_dict(payload)
    assert restored.parallel_policy == original.parallel_policy
    assert restored.as_dict()["parallel_policy"]["max_local_slots"] == 4


def test_manifest_reconcile_updates_static_contract_and_preserves_runtime_state(tmp_path: Path) -> None:
    runtime = CaseWorklistRuntime(tmp_path)
    old = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        revision=2,
        steps=[
            CaseStep(
                "010",
                "old director",
                allowed_actions=["old.director"],
                acceptance=["ok"],
                status=StepStatus.PASSED,
                evidence={"ok": True, "director_plan_sha256": "a" * 64},
            ),
            CaseStep("050", "old join", dependencies=["010"], allowed_actions=["old.bind"], acceptance=["ok"]),
        ],
        parallel_policy={"max_local_slots": 1},
    )
    runtime.store.save(old)

    latest = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        revision=4,
        steps=[
            CaseStep(
                "010",
                "new director",
                allowed_actions=["comfyx-studio.director.preproduction"],
                acceptance=["ok", "director_plan_sha256"],
            ),
            CaseStep(
                "050",
                "new atomic join",
                dependencies=["010"],
                allowed_actions=["comfyx-studio.storyboard.real-bind"],
                acceptance=["ok"],
            ),
        ],
        parallel_policy={"authority": "openworker-local-supervisor", "max_local_slots": 4},
    )

    reconciled = runtime.ensure(latest)
    assert reconciled.revision == 5
    assert reconciled.parallel_policy["max_local_slots"] == 4
    assert reconciled.step("010").status == StepStatus.PASSED
    assert reconciled.step("010").evidence["director_plan_sha256"] == "a" * 64
    assert reconciled.step("010").allowed_actions == ["comfyx-studio.director.preproduction"]
    assert reconciled.step("050").allowed_actions == ["comfyx-studio.storyboard.real-bind"]
    assert runtime.load().parallel_policy["authority"] == "openworker-local-supervisor"


def test_manifest_reconcile_rejects_replacing_active_running_action(tmp_path: Path) -> None:
    runtime = CaseWorklistRuntime(tmp_path)
    current = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[
            CaseStep(
                "010",
                "running",
                allowed_actions=["old.action"],
                acceptance=["ok"],
                status=StepStatus.RUNNING,
                evidence={
                    "__openworker_active_action": "old.action",
                    "__openworker_active_execution": "exec-old",
                },
            )
        ],
    )
    runtime.store.save(current)
    latest = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[CaseStep("010", "running", allowed_actions=["new.action"], acceptance=["ok"])],
    )
    with pytest.raises(CaseWorklistError, match="cannot replace active action"):
        runtime.ensure(latest)


def test_manifest_reconcile_preserves_dynamic_repair(tmp_path: Path) -> None:
    runtime = CaseWorklistRuntime(tmp_path)
    current = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[
            CaseStep("010", "root", allowed_actions=["a.root"], acceptance=["ok"], status=StepStatus.BLOCKED, blocker="broken"),
            CaseStep(
                "010-R1",
                "repair",
                kind="repair",
                dependencies=[],
                allowed_actions=["a.repair"],
                acceptance=["ok"],
                repair_parent_step="010",
                status=StepStatus.READY,
            ),
        ],
    )
    runtime.store.save(current)
    latest = CaseWorklist(
        case_id="0005",
        workspace_root=str(tmp_path),
        assigned_host="DESKTOP-ODAQN0D",
        steps=[CaseStep("010", "root v2", allowed_actions=["a.root"], acceptance=["ok"])],
        parallel_policy={"max_local_slots": 4},
    )
    reconciled = runtime.ensure(latest)
    assert reconciled.step("010-R1").kind == "repair"
    assert reconciled.step("010-R1").repair_parent_step == "010"
    assert reconciled.step("010").status == StepStatus.BLOCKED
