from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from coworker.personas.media_evidence import MediaEvidenceSyncError, sync_comfyx_media_evidence
from coworker.personas.submission import PersonaJobSubmission


def _submission() -> PersonaJobSubmission:
    return PersonaJobSubmission(
        project_id="project-1", job_id="job-1", reused=False,
        task_package_path="/workspace/.openworker/persona-tasks/media/s1/p1.json",
        persona="media", session_id="s1", handoff_capabilities=("media",),
    )


def _mp4(path: Path) -> bytes:
    payload = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"media-bytes"
    path.write_bytes(payload)
    return payload


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get_job(self, job_id: str) -> dict:
        return {
            "id": job_id, "project_id": "project-1", "status": "running",
            "metadata": {
                "persona": "media", "persona_session_id": "s1",
                "task_package_path": "/workspace/.openworker/persona-tasks/media/s1/p1.json",
            },
        }

    def register_artifact(self, **kwargs) -> dict:
        self.calls.append(dict(kwargs))
        return {
            "id": f"artifact-{len(self.calls)}",
            "project_id": kwargs["project_id"], "job_id": kwargs["job_id"],
            "kind": kwargs["kind"], "uri": kwargs["uri"],
            "media_type": kwargs["media_type"], "checksum": kwargs["checksum"],
            "source_run_id": kwargs["source_run_id"],
        }


def _result(uri: str, *, size: int | None = None, sha256: str | None = None) -> dict:
    artifact = {"uri": uri, "media_type": "video/mp4"}
    if size is not None:
        artifact["size"] = size
    if sha256 is not None:
        artifact["sha256"] = sha256
    return {
        "schema": "openworker.comfyx-h3-result/v1", "authority": "ComfyX",
        "tool_id": "comfyx.minimax_h3.generate", "request_id": "req-1",
        "prompt_id": "prompt-123", "artifacts": [artifact],
    }


def test_sync_registers_verified_mp4_under_existing_job_and_cross_checks_comfyx_metadata(tmp_path):
    path = tmp_path / "h3.mp4"
    payload = _mp4(path)
    checksum = hashlib.sha256(payload).hexdigest()
    writer = FakeWriter()

    synced = sync_comfyx_media_evidence(
        writer, _submission(), _result(str(path), size=len(payload), sha256=checksum)
    )

    assert len(writer.calls) == 1
    call = writer.calls[0]
    assert call["project_id"] == "project-1"
    assert call["job_id"] == "job-1"
    assert call["kind"] == "animation_video"
    assert call["media_type"] == "video/mp4"
    assert call["checksum"] == checksum
    assert call["source_run_id"] == "prompt-123"
    assert synced.prompt_id == "prompt-123"
    assert synced.artifacts[0].checksum == call["checksum"]
    assert synced.to_dict()["publish_performed"] is False
    assert synced.to_dict()["external_send_performed"] is False


def test_sync_rejects_comfyx_sha256_mismatch_before_registry_mutation(tmp_path):
    path = tmp_path / "h3.mp4"
    _mp4(path)
    writer = FakeWriter()
    with pytest.raises(MediaEvidenceSyncError, match="sha256 mismatch"):
        sync_comfyx_media_evidence(writer, _submission(), _result(str(path), sha256="0" * 64))
    assert writer.calls == []


def test_sync_rejects_comfyx_size_mismatch_before_registry_mutation(tmp_path):
    path = tmp_path / "h3.mp4"
    payload = _mp4(path)
    writer = FakeWriter()
    with pytest.raises(MediaEvidenceSyncError, match="size mismatch"):
        sync_comfyx_media_evidence(writer, _submission(), _result(str(path), size=len(payload) + 1))
    assert writer.calls == []


def test_sync_deduplicates_identical_local_artifacts(tmp_path):
    path = tmp_path / "h3.mp4"
    _mp4(path)
    result = _result(str(path))
    result["artifacts"].append({"path": str(path), "media_type": "video/mp4"})
    writer = FakeWriter()
    synced = sync_comfyx_media_evidence(writer, _submission(), result)
    assert len(writer.calls) == 1
    assert len(synced.artifacts) == 1


def test_sync_rejects_legacy_comfyx_view_only_artifact_instead_of_guessing_path():
    writer = FakeWriter()
    result = {
        "authority": "ComfyX", "tool_id": "comfyx.minimax_h3.generate",
        "request_id": "req", "prompt_id": "prompt",
        "artifacts": [{"filename": "h3.mp4", "subfolder": "video", "type": "output", "url": "/view?filename=h3.mp4"}],
    }
    with pytest.raises(MediaEvidenceSyncError, match="uri/path"):
        sync_comfyx_media_evidence(writer, _submission(), result)
    assert writer.calls == []


def test_sync_rejects_non_local_uri_without_downloading_or_hashing():
    writer = FakeWriter()
    with pytest.raises(MediaEvidenceSyncError, match="local file"):
        sync_comfyx_media_evidence(writer, _submission(), _result("https://example.invalid/h3.mp4"))
    assert writer.calls == []


def test_sync_rejects_truncated_mp4_before_registry_mutation(tmp_path):
    path = tmp_path / "bad.mp4"
    path.write_bytes(b"not-an-mp4")
    writer = FakeWriter()
    with pytest.raises(MediaEvidenceSyncError, match="invalid MP4"):
        sync_comfyx_media_evidence(writer, _submission(), _result(str(path)))
    assert writer.calls == []


def test_sync_rejects_wrong_job_lineage_before_registry_mutation(tmp_path):
    path = tmp_path / "h3.mp4"
    _mp4(path)

    class WrongWriter(FakeWriter):
        def get_job(self, job_id: str) -> dict:
            job = super().get_job(job_id)
            job["metadata"]["persona_session_id"] = "other-session"
            return job

    writer = WrongWriter()
    with pytest.raises(MediaEvidenceSyncError, match="lineage mismatch"):
        sync_comfyx_media_evidence(writer, _submission(), _result(str(path)))
    assert writer.calls == []


def test_sync_requires_media_capability(tmp_path):
    path = tmp_path / "h3.mp4"
    _mp4(path)
    submission = PersonaJobSubmission(
        project_id="project-1", job_id="job-1", reused=False, task_package_path="x",
        persona="company", session_id="s1", handoff_capabilities=("engineering",),
    )
    with pytest.raises(MediaEvidenceSyncError, match="media capability"):
        sync_comfyx_media_evidence(FakeWriter(), submission, _result(str(path)))
