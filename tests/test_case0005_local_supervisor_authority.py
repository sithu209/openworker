from pathlib import Path
from types import SimpleNamespace

from coworker.case0005_local_supervisor import Case0005LocalSupervisor, _MODULE


def _controller(tmp_path: Path) -> Case0005LocalSupervisor:
    controller = object.__new__(Case0005LocalSupervisor)
    controller.workspace = tmp_path.resolve()
    controller.openworker_root = (tmp_path / "openworker").resolve()
    controller._localexec_env = lambda: {"GTR_WORK_QUEUE_URL": "http://127.0.0.1:8848"}
    return controller


def test_all_child_payloads_reenter_stable_local_supervisor(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    worklist = SimpleNamespace(case_id="0005", assigned_host="DESKTOP-ODAQN0D")
    step = SimpleNamespace(step_id="0005-020", kind="work")
    claim = tmp_path / "claim.json"
    manifest = tmp_path / "fanout.json"

    generic = controller._job_payload(worklist, step, "comfyx-studio.storyboard.plan", "case0005-generic", claim)
    image = controller._image_child_payload(
        worklist=worklist,
        step_id="0005-030",
        group_id="case0005-image-group",
        child_id="case0005-image-child",
        asset_id="snow-white",
        role="character_master",
        claim_path=claim,
        manifest_path=manifest,
    )
    video = controller._video_child_payload(
        worklist=worklist,
        group_id="case0005-video-group",
        child_id="case0005-video-child",
        shot_id="shot-001",
        claim_path=claim,
        manifest_path=manifest,
    )

    for payload in (generic, image, video):
        assert _MODULE in payload["command"]
        assert payload["machine"] == "DESKTOP-ODAQN0D"
        assert payload["workspace_root"] == str(tmp_path.resolve())
        assert payload["env"]["GTR_WORK_QUEUE_URL"] == "http://127.0.0.1:8848"
