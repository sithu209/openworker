"""H9 ComfyX long-running media verification.

AI-Engineering-OS remains the durable Job/Artifact authority.  ComfyX/ComfyUI
remain the specialist runtime.  A media run is successful only when OS reaches
an acceptable state and exposes at least one non-empty ISO-BMFF MP4 artifact
whose checksum matches the durable Artifact record.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .engineering_os import EngineeringOSClient


class ComfyXLongJobError(RuntimeError):
    pass


class ComfyXArtifactError(ComfyXLongJobError):
    pass


@dataclass(frozen=True)
class VerifiedMP4:
    artifact_id: str
    uri: str
    size: int
    sha256: str
    major_brand: str


@dataclass(frozen=True)
class ComfyXLongJobReport:
    project_id: str
    job_id: str
    job_status: str
    execution_id: str | None
    plan_id: str | None
    videos: tuple[VerifiedMP4, ...]
    manifest_artifact_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "job_id": self.job_id,
            "job_status": self.job_status,
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "manifest_artifact_id": self.manifest_artifact_id,
            "videos": [video.__dict__ for video in self.videos],
        }


class EngineeringMediaObserver(Protocol):
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def list_job_artifacts(self, job_id: str) -> Sequence[dict[str, Any]]: ...


class ComfyXCLIError(ComfyXLongJobError):
    pass


class ComfyXCLIClient:
    """Thin client for ComfyX's existing model-facing job.status/job.cancel CLIs."""

    def __init__(
        self,
        *,
        status_executable: str = "comfyx-job-status",
        cancel_executable: str = "comfyx-job-cancel",
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.status_executable = status_executable
        self.cancel_executable = cancel_executable
        self.base_url = (base_url or "").strip()
        self.timeout_seconds = timeout_seconds

    def _run(self, executable: str, prompt_id: str) -> dict[str, Any]:
        prompt_id = prompt_id.strip()
        if not prompt_id:
            raise ValueError("prompt_id must not be empty")
        args = [executable, "--prompt-id", prompt_id]
        if self.base_url:
            args.extend(["--url", self.base_url])
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ComfyXCLIError(f"ComfyX CLI failed: {exc}") from exc
        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ComfyXCLIError(
                f"ComfyX CLI returned invalid JSON; stderr={completed.stderr.strip()[:500]}"
            ) from exc
        if not isinstance(payload, dict):
            raise ComfyXCLIError("ComfyX CLI response must be an object")
        if completed.returncode != 0 or payload.get("status") == "failed":
            error = payload.get("error")
            raise ComfyXCLIError(f"ComfyX CLI failed: {error or completed.stderr.strip()}")
        return payload

    def status(self, prompt_id: str) -> dict[str, Any]:
        payload = self._run(self.status_executable, prompt_id)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ComfyXCLIError("comfyx.job.status response missing data object")
        return data

    def cancel(self, prompt_id: str) -> dict[str, Any]:
        payload = self._run(self.cancel_executable, prompt_id)
        if payload.get("status") != "accepted":
            raise ComfyXCLIError(f"comfyx.job.cancel was not accepted: {payload.get('status')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ComfyXCLIError("comfyx.job.cancel response missing data object")
        return data


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ComfyXLongJobError(f"missing required {field}")
    return value.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_mp4(path: str | os.PathLike[str]) -> tuple[int, str]:
    """Validate an ISO Base Media File Format header, not merely `.mp4` suffix."""
    target = Path(path)
    try:
        stat = target.stat()
    except OSError as exc:
        raise ComfyXArtifactError(f"video artifact does not exist: {target}: {exc}") from exc
    if not target.is_file():
        raise ComfyXArtifactError(f"video artifact is not a regular file: {target}")
    if stat.st_size < 12:
        raise ComfyXArtifactError(f"video artifact is empty/truncated: {target} ({stat.st_size} bytes)")
    with target.open("rb") as handle:
        prefix = handle.read(64)
    # ISO BMFF starts with a box: 4-byte big-endian size + 4-byte type.  MP4
    # commonly begins with ftyp; allow a small leading free/wide box by finding
    # ftyp within the first 64 bytes, but require a plausible box boundary.
    offset = prefix.find(b"ftyp")
    if offset < 4 or offset > 32:
        raise ComfyXArtifactError(f"video artifact is not recognizable ISO-BMFF MP4: {target}")
    box_start = offset - 4
    box_size = int.from_bytes(prefix[box_start:offset], "big")
    if box_size != 0 and box_size < 8:
        raise ComfyXArtifactError(f"invalid MP4 ftyp box size {box_size}: {target}")
    if len(prefix) < offset + 8:
        raise ComfyXArtifactError(f"MP4 ftyp box is truncated: {target}")
    brand_bytes = prefix[offset + 4:offset + 8]
    try:
        major_brand = brand_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ComfyXArtifactError(f"MP4 major brand is not ASCII: {target}") from exc
    if not major_brand.strip("\x00 "):
        raise ComfyXArtifactError(f"MP4 major brand is empty: {target}")
    return stat.st_size, major_brand


def _artifact_local_path(artifact: Mapping[str, Any]) -> Path:
    uri = _required_text(artifact.get("uri"), "artifact.uri")
    if uri.startswith("file://"):
        uri = uri[7:]
        if os.name == "nt" and uri.startswith("/") and len(uri) > 2 and uri[2] == ":":
            uri = uri[1:]
    if "://" in uri:
        raise ComfyXArtifactError(
            f"H9 local GPU verification requires a local artifact URI, got {uri!r}"
        )
    return Path(uri)


def verify_video_artifact(artifact: Mapping[str, Any]) -> VerifiedMP4:
    artifact_id = _required_text(artifact.get("id"), "artifact.id")
    kind = _required_text(artifact.get("kind"), "artifact.kind").lower()
    media_type = str(artifact.get("media_type") or "").lower()
    uri = _required_text(artifact.get("uri"), "artifact.uri")
    if kind != "animation_video" and media_type not in {"video/mp4", "application/mp4"}:
        raise ComfyXArtifactError(f"artifact {artifact_id} is not an MP4 video artifact")
    path = _artifact_local_path(artifact)
    size, major_brand = inspect_mp4(path)
    actual_sha = _sha256_file(path)
    expected_sha = _required_text(artifact.get("checksum"), "artifact.checksum").lower()
    if actual_sha.lower() != expected_sha:
        raise ComfyXArtifactError(
            f"artifact {artifact_id} checksum mismatch: OS={expected_sha} local={actual_sha}"
        )
    return VerifiedMP4(artifact_id, uri, size, actual_sha, major_brand)


def _read_json_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    path = _artifact_local_path(artifact)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComfyXArtifactError(f"invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ComfyXArtifactError(f"JSON artifact must contain an object: {path}")
    return payload


def verify_comfyx_long_job(
    observer: EngineeringMediaObserver,
    *,
    project_id: str,
    job_id: str,
) -> ComfyXLongJobReport:
    project_id = project_id.strip()
    job_id = job_id.strip()
    if not project_id or not job_id:
        raise ValueError("project_id and job_id must not be empty")
    job = observer.get_job(job_id)
    if _required_text(job.get("id"), "job.id") != job_id:
        raise ComfyXLongJobError("Engineering-OS returned inconsistent job id")
    if _required_text(job.get("project_id"), "job.project_id") != project_id:
        raise ComfyXLongJobError("Engineering-OS returned inconsistent project id")
    status = _required_text(job.get("status"), "job.status")
    if status in {"cancelled", "archived"}:
        raise ComfyXLongJobError(f"cancelled/archived media job cannot be reported successful: {status}")
    if status not in {"review", "completed", "published"}:
        raise ComfyXLongJobError(f"media job has not reached a successful durable state: {status}")

    artifacts = list(observer.list_job_artifacts(job_id))
    video_artifacts = [
        artifact for artifact in artifacts
        if str(artifact.get("kind") or "").lower() == "animation_video"
        or str(artifact.get("media_type") or "").lower() in {"video/mp4", "application/mp4"}
    ]
    if not video_artifacts:
        raise ComfyXLongJobError("media job has no MP4 video artifact")
    videos = tuple(verify_video_artifact(artifact) for artifact in video_artifacts)

    manifest_artifact = next(
        (artifact for artifact in artifacts if artifact.get("kind") == "animation_media_manifest"),
        None,
    )
    execution_artifact = next(
        (artifact for artifact in artifacts if artifact.get("kind") == "animation_comfyx_execution"),
        None,
    )
    manifest = _read_json_artifact(manifest_artifact) if manifest_artifact else {}
    execution = _read_json_artifact(execution_artifact) if execution_artifact else {}
    execution_id = str(manifest.get("comfyx_execution_id") or execution.get("execution_id") or "").strip() or None
    plan_id = str(manifest.get("comfyx_plan_id") or execution.get("plan_id") or "").strip() or None
    if execution_artifact and execution.get("status") not in (None, "succeeded"):
        raise ComfyXLongJobError(
            f"ComfyX execution artifact is not succeeded: {execution.get('status')}"
        )
    return ComfyXLongJobReport(
        project_id=project_id,
        job_id=job_id,
        job_status=status,
        execution_id=execution_id,
        plan_id=plan_id,
        videos=videos,
        manifest_artifact_id=(str(manifest_artifact.get("id")) if manifest_artifact else None),
    )


def verify_with_engineering_os(
    client: EngineeringOSClient,
    *,
    project_id: str,
    job_id: str,
) -> ComfyXLongJobReport:
    return verify_comfyx_long_job(client, project_id=project_id, job_id=job_id)


__all__ = [
    "ComfyXArtifactError",
    "ComfyXCLIClient",
    "ComfyXCLIError",
    "ComfyXLongJobError",
    "ComfyXLongJobReport",
    "VerifiedMP4",
    "inspect_mp4",
    "verify_comfyx_long_job",
    "verify_video_artifact",
    "verify_with_engineering_os",
]
