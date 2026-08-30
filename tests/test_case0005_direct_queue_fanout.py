from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coworker.case0005_direct_queue_fanout import Case0005DirectQueueFanoutMixin


class _Runtime:
    def __init__(self):
        self.records = []
        self.started = []

    def start_action(self, step_id, action, execution_id):
        self.started.append((step_id, action, execution_id))

    def record(self, step_id, key, value):
        self.records.append((step_id, key, value))


class _Node:
    def __init__(self):
        self.payloads = []

    def submit(self, payload):
        self.payloads.append(payload)
        return {"accepted": True, "job_id": payload["job_id"]}


class _Harness(Case0005DirectQueueFanoutMixin):
    def __init__(self, root: Path):
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True)
        self.openworker_root = root / "openworker"
        self.runtime = _Runtime()
        self.node = _Node()
        self.queue_submissions = []
        self.ledger = []

    def _visual_assets_for_role(self, role):
        return [f"asset-{i}" for i in range(1, 6)]

    def _approved_video_shots(self):
        return [
            {"shot_id": f"shot-{i}", "first_frame_relpath": f"frames/{i}.png", "first_frame_sha256": "a" * 64}
            for i in range(1, 7)
        ]

    def _execution_id(self, case_id, step_id, action, revision):
        return f"case{case_id}-{step_id}-r{revision}"

    def _safe_id(self, value):
        return str(value).replace("/", "-")

    def _write_json_atomic(self, path, value):
        import json
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def _localexec_env(self):
        return {}

    def _append_ledger(self, event_type, **fields):
        self.ledger.append((event_type, fields))

    def _queue_submit(self, *, work_id, assigned_host, capability_id, inputs):
        item = {"work_id": work_id, "assigned_host": assigned_host, "capability_id": capability_id, "status": "pending"}
        self.queue_submissions.append((work_id, capability_id, dict(inputs)))
        return item


def _worklist():
    return SimpleNamespace(case_id="0005", assigned_host="DESKTOP-ODAQN0D", revision=6, parallel_policy={"max_local_slots": 4})


def test_image_fanout_puts_all_business_items_in_local_queue_before_one_coordinator(tmp_path: Path):
    h = _Harness(tmp_path)
    step = SimpleNamespace(step_id="0005-030")
    result = h._dispatch_image_fanout(_worklist(), step, "image.comfyx.storyboard-real", "character_master")
    assert len(h.queue_submissions) == 5
    assert len(h.node.payloads) == 1
    assert h.node.payloads[0]["job_id"].endswith("--queue-coordinator")
    assert "watch-image-fanout" in h.node.payloads[0]["command"]
    assert result["queue_owns_all_children"] is True
    assert result["max_local_slots"] == 4
    assert all(item[1] == "image.comfyx.storyboard-real" for item in h.queue_submissions)


def test_video_fanout_puts_all_shots_in_local_queue_before_one_coordinator(tmp_path: Path):
    h = _Harness(tmp_path)
    step = SimpleNamespace(step_id="0005-060")
    result = h._dispatch_video_fanout(_worklist(), step, "comfyx.production.video.real")
    assert len(h.queue_submissions) == 6
    assert len(h.node.payloads) == 1
    assert h.node.payloads[0]["job_id"].endswith("--queue-coordinator")
    assert "watch-video-fanout" in h.node.payloads[0]["command"]
    assert result["queue_owns_all_children"] is True
    assert result["max_local_slots"] == 4
    assert all(item[1] == "comfyx.production.video.real" for item in h.queue_submissions)
