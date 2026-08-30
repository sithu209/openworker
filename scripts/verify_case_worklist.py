from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coworker.case_worklist import (
    CaseStep,
    CaseWorklist,
    CaseWorklistError,
    CaseWorklistStore,
    StepStatus,
)
from coworker.case_worklist_runtime import CaseWorklistRuntime


def expect_error(fn, contains: str) -> None:
    try:
        fn()
    except CaseWorklistError as exc:
        if contains not in str(exc):
            raise AssertionError(f"expected error containing {contains!r}, got {exc!r}") from exc
        return
    raise AssertionError(f"expected CaseWorklistError containing {contains!r}")


def build(workspace: Path) -> CaseWorklist:
    return CaseWorklist(
        case_id="verify",
        workspace_root=str(workspace),
        assigned_host="HOST",
        steps=[
            CaseStep(
                step_id="010",
                title="multi action",
                allowed_actions=["action.one", "action.two"],
                acceptance=["proof"],
            ),
            CaseStep(
                step_id="020",
                title="later",
                dependencies=["010"],
                allowed_actions=["action.later"],
                acceptance=["later_proof"],
            ),
        ],
    )


def verify_state_machine(workspace: Path) -> None:
    worklist = build(workspace)
    assert worklist.next_step() is not None
    assert worklist.next_step().step_id == "010"
    expect_error(
        lambda: worklist.assert_action_allowed("020", "action.later"),
        "case drift blocked",
    )

    worklist.start("010", "action.one")
    assert worklist.step("010").status == StepStatus.RUNNING
    assert worklist.next_step().step_id == "010"

    revision = worklist.revision
    worklist.start("010", "action.two")
    assert worklist.revision == revision, "re-entering same RUNNING step must be idempotent"
    expect_error(
        lambda: worklist.assert_action_allowed("020", "action.later"),
        "case drift blocked",
    )

    expect_error(lambda: worklist.pass_step("010"), "missing acceptance evidence")
    worklist.record_evidence("010", "proof", "ok")
    worklist.pass_step("010")
    assert worklist.next_step().step_id == "020"

    expect_error(
        lambda: worklist.record_evidence("020", "later_proof", "too early"),
        "cannot record evidence",
    )
    expect_error(lambda: worklist.pass_step("020"), "cannot pass")

    store = CaseWorklistStore(workspace)
    store.save(worklist)
    loaded = store.load()
    assert loaded.next_step().step_id == "020"
    persisted = json.loads(store.path.read_text(encoding="utf-8"))
    assert persisted["canonical_next_step_id"] == "020"

    payload = loaded.as_dict()
    payload["steps"][0]["status"] = "RUNNING"
    payload["steps"][1]["status"] = "RUNNING"
    expect_error(lambda: CaseWorklist.from_dict(payload), "multiple RUNNING")


def verify_runtime_serialization(workspace: Path) -> None:
    runtime = CaseWorklistRuntime(workspace)
    runtime.ensure(build(workspace))

    runtime.start_action("010", "action.one", execution_id="exec-1")
    current = runtime.load()
    assert current.step("010").status == StepStatus.RUNNING
    assert current.step("010").evidence["__openworker_active_action"] == "action.one"

    # Exact retry by the same execution is idempotent.
    runtime.start_action("010", "action.one", execution_id="exec-1")

    # A second workflow/action cannot overlap the active action, even though the
    # second action belongs to the same valid multi-action stage.
    expect_error(
        lambda: runtime.start_action("010", "action.two", execution_id="exec-2"),
        "case action concurrency blocked",
    )

    runtime.complete_action("010", "action.one", execution_id="exec-1")
    runtime.start_action("010", "action.two", execution_id="exec-2")
    expect_error(
        lambda: runtime.complete_action("010", "action.two", execution_id="wrong-owner"),
        "active action ownership mismatch",
    )
    runtime.complete_action("010", "action.two", execution_id="exec-2")
    runtime.record("010", "proof", "serialized")
    runtime.pass_step("010")
    assert runtime.load().next_step().step_id == "020"

    # The filesystem lock itself must fail closed when another mutator owns it.
    impatient = CaseWorklistRuntime(workspace, lock_timeout=0.05, stale_after=3600.0)
    with runtime.lock():
        expect_error(lambda: _take_lock(impatient), "mutation lock timeout")


def _take_lock(runtime: CaseWorklistRuntime) -> None:
    with runtime.lock():
        pass


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="openworker-worklist-") as raw:
        root = Path(raw)
        state_workspace = root / "state"
        state_workspace.mkdir()
        verify_state_machine(state_workspace)

        runtime_workspace = root / "runtime"
        runtime_workspace.mkdir()
        verify_runtime_serialization(runtime_workspace)

    print("CASE_WORKLIST_FOCUSED_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
