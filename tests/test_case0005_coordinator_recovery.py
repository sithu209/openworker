from __future__ import annotations

from pathlib import Path

from coworker.case0005_coordinator_recovery import Case0005CoordinatorRecoveryMixin


class _Harness(Case0005CoordinatorRecoveryMixin):
    def __init__(self, states):
        self.states = states

    def _queue_get(self, work_id):
        return self.states[work_id]


def _manifest():
    return {
        "assigned_host": "DESKTOP-ODAQN0D",
        "action_id": "image.comfyx.storyboard-real",
        "jobs": [
            {"queue_work_id": "case0005-a"},
            {"queue_work_id": "case0005-b"},
        ],
    }


def test_complete_queue_proof_accepts_pending_claimed_completed_only():
    h = _Harness({
        "case0005-a": {"work_id":"case0005-a","assigned_host":"DESKTOP-ODAQN0D","capability_id":"image.comfyx.storyboard-real","status":"claimed","attempts":1},
        "case0005-b": {"work_id":"case0005-b","assigned_host":"DESKTOP-ODAQN0D","capability_id":"image.comfyx.storyboard-real","status":"completed","attempts":1},
    })
    proof = h._prove_all_queue_children(_manifest())
    assert proof is not None
    assert proof["all_manifest_children_durable"] is True
    assert proof["no_business_child_failed"] is True
    assert proof["child_count"] == 2


def test_business_failure_is_not_coordinator_recoverable():
    h = _Harness({
        "case0005-a": {"work_id":"case0005-a","assigned_host":"DESKTOP-ODAQN0D","capability_id":"image.comfyx.storyboard-real","status":"failed","attempts":1},
        "case0005-b": {"work_id":"case0005-b","assigned_host":"DESKTOP-ODAQN0D","capability_id":"image.comfyx.storyboard-real","status":"completed","attempts":1},
    })
    assert h._prove_all_queue_children(_manifest()) is None


def test_wrong_identity_is_not_recoverable():
    h = _Harness({
        "case0005-a": {"work_id":"case0005-a","assigned_host":"OTHER","capability_id":"image.comfyx.storyboard-real","status":"pending"},
        "case0005-b": {"work_id":"case0005-b","assigned_host":"DESKTOP-ODAQN0D","capability_id":"image.comfyx.storyboard-real","status":"pending"},
    })
    assert h._prove_all_queue_children(_manifest()) is None


def test_only_coordinator_submit_blocker_can_resume():
    assert Case0005CoordinatorRecoveryMixin._is_coordinator_submit_blocker(
        "direct local queue image fanout submit failed: OpenWorker unavailable"
    )
    assert Case0005CoordinatorRecoveryMixin._is_coordinator_submit_blocker(
        "direct local queue video fanout submit failed: OpenWorker unavailable"
    )
    assert not Case0005CoordinatorRecoveryMixin._is_coordinator_submit_blocker(
        "image fanout child failure: asset-1 failed"
    )
