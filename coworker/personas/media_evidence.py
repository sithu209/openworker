"""E7.7/E7.8 verified ComfyX result -> AI-Engineering-OS Artifact Registry sync.

ComfyX remains the media execution authority and AI-Engineering-OS remains the durable
Job/Artifact authority. This module reconciles one successful media result into the
already-created canonical Job. It never publishes, sends, creates another Job, or invents
an artifact URI/checksum when ComfyX did not provide durable evidence.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import unquote, urlparse

from coworker.engineering.comfyx_long_job import inspect_mp4
from coworker.engineering.digital_thread import EvidenceRef, os_artifact_ref

from .submission import PersonaJobSubmission, SubmissionContractError


class MediaEvidenceSyncError(SubmissionContractError):
    """Raised when ComfyX output cannot be reconciled into canonical evidence safely."""


class MediaArtifactWriter(Protocol):
    def get_job(self, job_id: str) -> dict[str, Any]: ...
    def register_artifact(
        self, *, project_id: str, job_id: str | None, component_id: str | None,
        kind: str, uri: str, media_type: str, checksum: str,
        source_run_id: str | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MediaEvidenceSyncResult:
    submission: PersonaJobSubmission
    prompt_id: str
    request_id: str
    artifacts: tuple[EvidenceRef, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.persona-media-evidence-sync/v1",
            "authority": "AI-Engineering-OS",
            "media_authority": "ComfyX",
            "submission": self.submission.to_dict(),
            "prompt_id": self.prompt_id,
            "request_id": self.request_id,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "publish_performed": False,
            "external_send_performed": False,
        }


def _required_text(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise MediaEvidenceSyncError(f"{field} must not be empty")
    return text


def _local_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme.lower() != "file":
        raise MediaEvidenceSyncError(f"media artifact must be a local file URI/path, got {uri!r}")
    if parsed.scheme.lower() == "file":
        path = unquote(parsed.path)
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return Path(path)
    return Path(uri)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise MediaEvidenceSyncError(f"cannot read media artifact {path}: {exc}") from exc
    return digest.hexdigest()


def _artifact_uri(raw: Mapping[str, Any]) -> str:
    value = raw.get("uri") or raw.get("path")
    return _required_text(value, "comfyx artifact uri/path")


def _media_type(path: Path, raw: Mapping[str, Any]) -> str:
    explicit = str(raw.get("media_type") or "").strip().lower()
    if explicit:
        return explicit
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _kind(media_type: str) -> str:
    return "animation_video" if media_type in {"video/mp4", "application/mp4"} else "media_output"


def _validate_job(writer: MediaArtifactWriter, submission: PersonaJobSubmission) -> None:
    job = writer.get_job(submission.job_id)
    if _required_text(job.get("id"), "job.id") != submission.job_id:
        raise MediaEvidenceSyncError("canonical Job id does not match persona submission")
    if _required_text(job.get("project_id"), "job.project_id") != submission.project_id:
        raise MediaEvidenceSyncError("canonical Job project_id does not match persona submission")
    metadata = job.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise MediaEvidenceSyncError("canonical Job metadata must be an object")
    metadata = metadata or {}
    for key, expected in {
        "persona": submission.persona,
        "persona_session_id": submission.session_id,
        "task_package_path": submission.task_package_path,
    }.items():
        actual = metadata.get(key)
        if actual is not None and str(actual) != str(expected):
            raise MediaEvidenceSyncError(f"canonical Job lineage mismatch: {key}")


def sync_comfyx_media_evidence(
    writer: MediaArtifactWriter,
    submission: PersonaJobSubmission,
    result: Mapping[str, Any],
) -> MediaEvidenceSyncResult:
    """Register verified local ComfyX outputs under the existing canonical Job."""

    if "media" not in submission.handoff_capabilities:
        raise MediaEvidenceSyncError("submission does not declare media capability")
    if not isinstance(result, Mapping):
        raise MediaEvidenceSyncError("ComfyX result must be an object")
    if result.get("authority") != "ComfyX":
        raise MediaEvidenceSyncError("media result authority must be ComfyX")
    if result.get("tool_id") != "comfyx.minimax_h3.generate":
        raise MediaEvidenceSyncError("media result tool_id is not authoritative MiniMax H3")
    prompt_id = _required_text(result.get("prompt_id"), "media result prompt_id")
    request_id = _required_text(result.get("request_id"), "media result request_id")
    artifacts_raw = result.get("artifacts")
    if not isinstance(artifacts_raw, Sequence) or isinstance(artifacts_raw, (str, bytes)):
        raise MediaEvidenceSyncError("media result artifacts must be an array")
    if not artifacts_raw:
        raise MediaEvidenceSyncError("media result contains no artifacts")

    _validate_job(writer, submission)
    registered: list[EvidenceRef] = []
    seen: set[tuple[str, str]] = set()
    for raw in artifacts_raw:
        if not isinstance(raw, Mapping):
            raise MediaEvidenceSyncError("ComfyX artifact must be an object")
        uri = _artifact_uri(raw)
        path = _local_path(uri)
        if not path.is_file():
            raise MediaEvidenceSyncError(f"media artifact does not exist: {path}")
        stat = path.stat()
        declared_size = raw.get("size")
        if declared_size is not None:
            if not isinstance(declared_size, int) or declared_size <= 0:
                raise MediaEvidenceSyncError("ComfyX artifact size must be a positive integer")
            if declared_size != stat.st_size:
                raise MediaEvidenceSyncError(
                    f"ComfyX artifact size mismatch: declared={declared_size} local={stat.st_size}"
                )
        media_type = _media_type(path, raw)
        if media_type in {"video/mp4", "application/mp4"}:
            try:
                inspect_mp4(path)
            except Exception as exc:
                raise MediaEvidenceSyncError(f"invalid MP4 media artifact {path}: {exc}") from exc
        checksum = _sha256_file(path)
        declared_sha = str(raw.get("sha256") or "").strip().lower()
        if declared_sha and declared_sha != checksum.lower():
            raise MediaEvidenceSyncError(
                f"ComfyX artifact sha256 mismatch: declared={declared_sha} local={checksum}"
            )
        dedupe_key = (str(path.resolve()), checksum)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        artifact = writer.register_artifact(
            project_id=submission.project_id,
            job_id=submission.job_id,
            component_id=None,
            kind=_kind(media_type),
            uri=uri,
            media_type=media_type,
            checksum=checksum,
            source_run_id=prompt_id,
        )
        try:
            registered.append(os_artifact_ref(artifact))
        except (TypeError, ValueError) as exc:
            raise MediaEvidenceSyncError(f"AI-Engineering-OS returned invalid artifact evidence: {exc}") from exc

    if not registered:
        raise MediaEvidenceSyncError("media result produced no unique registrable artifacts")
    return MediaEvidenceSyncResult(
        submission=submission,
        prompt_id=prompt_id,
        request_id=request_id,
        artifacts=tuple(registered),
    )


__all__ = ["MediaArtifactWriter", "MediaEvidenceSyncError", "MediaEvidenceSyncResult", "sync_comfyx_media_evidence"]
