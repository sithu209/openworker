from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coworker.engineering.comfyx_long_job import (
    ComfyXArtifactError,
    ComfyXLongJobError,
    inspect_mp4,
    verify_comfyx_long_job,
)


def _mp4_bytes() -> bytes:
    # Minimal recognizable ISO-BMFF header plus a small free box. It is not a
    # playable movie; unit tests validate the container-evidence gate only.
    return (
        (24).to_bytes(4, "big") + b"ftyp" + b"isom" + (0).to_bytes(4, "big") + b"isommp42"
        + (12).to_bytes(4, "big") + b"free" + b"test"
    )


def _artifact(path: Path, *, artifact_id: str = "video-1") -> dict:
    body = path.read_bytes()
    return {
        "id": artifact_id,
        "kind": "animation_video",
        "uri": str(path),
        "media_type": "video/mp4",
        "checksum": hashlib.sha256(body).hexdigest(),
    }


class Observer:
    def __init__(self, artifacts, *, status="review"):
        self.artifacts = list(artifacts)
        self.status = status

    def get_job(self, job_id):
        return {"id": job_id, "project_id": "project-1", "status": self.status}

    def list_job_artifacts(self, _job_id):
        return list(self.artifacts)


def test_inspect_mp4_rejects_zero_byte_and_fake_extension(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(ComfyXArtifactError, match="empty/truncated"):
        inspect_mp4(empty)

    fake = tmp_path / "fake.mp4"
    fake.write_text("this is not a movie", encoding="utf-8")
    with pytest.raises(ComfyXArtifactError, match="not recognizable"):
        inspect_mp4(fake)


def test_inspect_mp4_accepts_iso_bmff_header(tmp_path: Path) -> None:
    video = tmp_path / "ok.mp4"
    video.write_bytes(_mp4_bytes())
    size, brand = inspect_mp4(video)
    assert size == len(_mp4_bytes())
    assert brand == "isom"


def test_completed_os_job_requires_nonempty_verified_video(tmp_path: Path) -> None:
    video = tmp_path / "result.mp4"
    video.write_bytes(_mp4_bytes())
    report = verify_comfyx_long_job(
        Observer([_artifact(video)]),
        project_id="project-1",
        job_id="job-1",
    )
    assert report.job_status == "review"
    assert report.videos[0].size > 0
    assert report.videos[0].major_brand == "isom"


def test_checksum_mismatch_fails_even_when_mp4_header_is_valid(tmp_path: Path) -> None:
    video = tmp_path / "result.mp4"
    video.write_bytes(_mp4_bytes())
    artifact = _artifact(video)
    artifact["checksum"] = "0" * 64
    with pytest.raises(ComfyXArtifactError, match="checksum mismatch"):
        verify_comfyx_long_job(Observer([artifact]), project_id="project-1", job_id="job-1")


def test_cancelled_job_never_reuses_stale_success_video(tmp_path: Path) -> None:
    video = tmp_path / "stale.mp4"
    video.write_bytes(_mp4_bytes())
    with pytest.raises(ComfyXLongJobError, match="cancelled/archived"):
        verify_comfyx_long_job(
            Observer([_artifact(video)], status="cancelled"),
            project_id="project-1",
            job_id="job-1",
        )


def test_completed_without_video_is_not_success() -> None:
    with pytest.raises(ComfyXLongJobError, match="no MP4"):
        verify_comfyx_long_job(
            Observer([], status="completed"), project_id="project-1", job_id="job-1"
        )


def test_execution_and_manifest_must_not_report_failed(tmp_path: Path) -> None:
    video = tmp_path / "result.mp4"
    video.write_bytes(_mp4_bytes())
    execution = tmp_path / "execution.json"
    execution.write_text(json.dumps({"execution_id": "exec-1", "plan_id": "plan-1", "status": "failed"}), encoding="utf-8")
    artifacts = [
        _artifact(video),
        {
            "id": "exec-a",
            "kind": "animation_comfyx_execution",
            "uri": str(execution),
            "media_type": "application/json",
            "checksum": hashlib.sha256(execution.read_bytes()).hexdigest(),
        },
    ]
    with pytest.raises(ComfyXLongJobError, match="not succeeded"):
        verify_comfyx_long_job(Observer(artifacts), project_id="project-1", job_id="job-1")


def test_manifest_exposes_comfyx_execution_identity(tmp_path: Path) -> None:
    video = tmp_path / "result.mp4"
    video.write_bytes(_mp4_bytes())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"comfyx_execution_id": "exec-9", "comfyx_plan_id": "plan-9"}), encoding="utf-8")
    artifacts = [
        _artifact(video),
        {
            "id": "manifest-a",
            "kind": "animation_media_manifest",
            "uri": str(manifest),
            "media_type": "application/json",
            "checksum": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    ]
    report = verify_comfyx_long_job(Observer(artifacts), project_id="project-1", job_id="job-1")
    assert report.execution_id == "exec-9"
    assert report.plan_id == "plan-9"
    assert report.manifest_artifact_id == "manifest-a"
