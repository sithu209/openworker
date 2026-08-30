"""Governed engineering-source ingress for OpenWorker jobs.

This module does not parse or transform product files.  It binds one OpenWorker
workspace to one AI-Engineering-OS Project/Job and one host, materializes an
immutable canonical source copy, imports the same bytes through the existing OS
Job Input API, registers the OS-owned input as an artifact, and records durable
OpenWorker project knowledge.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from coworker.runtimes.engineering_scope import EngineeringOSScopeClient, EngineeringScope
from coworker.runtimes.job_binding import JobBinding, JobBindingStore
from coworker.runtimes.project_knowledge import ProjectKnowledgeStore


class SourceIngressError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceIngressResult:
    schema_version: str
    project_id: str
    project_code: str
    job_id: str
    job_code: str
    assigned_host: str
    workspace_root: str
    canonical_path: str
    original_name: str
    media_type: str
    size: int
    sha256: str
    header: str
    os_input_id: str
    os_input_relative_path: str
    os_artifact_id: str
    os_artifact_revision: int
    already_materialized: bool
    already_imported: bool
    already_registered: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_leaf(value: str, *, fallback: str) -> str:
    leaf = Path(str(value or "").strip()).name
    if not leaf or leaf in {".", ".."}:
        raise SourceIngressError(f"invalid file name: {value!r}")
    if any(ch in leaf for ch in ("/", "\\", "\x00")):
        raise SourceIngressError(f"unsafe file name: {value!r}")
    return leaf or fallback


def _json_object(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceIngressError(f"{operation} returned non-JSON response") from exc
    if response.is_error:
        raise SourceIngressError(f"{operation} failed ({response.status_code}): {payload}")
    if not isinstance(payload, dict):
        raise SourceIngressError(f"{operation} must return a JSON object")
    return payload


class EngineeringSourceIngress:
    """Materialize one immutable source into an OpenWorker/OS job scope.

    Exact retries are idempotent.  A different byte stream may never overwrite
    an existing canonical source path or masquerade as the same OS input.
    """

    def __init__(
        self,
        *,
        os_url: str,
        workspace: str | os.PathLike[str],
        assigned_host: str,
        user_request: str,
        token: str = "",
        timeout_s: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.assigned_host = str(assigned_host or "").strip()
        self.user_request = str(user_request or "").strip()
        if not self.assigned_host:
            raise SourceIngressError("assigned_host is required")
        if not self.user_request:
            raise SourceIngressError("user_request is required")
        base = str(os_url or "").strip().rstrip("/")
        if not base:
            raise SourceIngressError("os_url is required")
        self.os_url = base
        self.token = str(token or "").strip()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_s, headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _host_gate(self) -> str:
        actual = JobBindingStore.current_host().strip()
        if not actual:
            raise SourceIngressError("cannot determine current host")
        if actual.casefold() != self.assigned_host.casefold():
            raise SourceIngressError(
                f"assigned host is {self.assigned_host}; current host is {actual}"
            )
        return actual

    def _scope_and_binding(self) -> tuple[EngineeringScope, JobBinding]:
        self.workspace.mkdir(parents=True, exist_ok=True)
        store = JobBindingStore(self.workspace)
        binding = store.load()
        if binding is not None:
            if binding.assigned_host.casefold() != self.assigned_host.casefold():
                raise SourceIngressError(
                    f"existing binding host {binding.assigned_host} != requested {self.assigned_host}"
                )
            return binding.scope(), binding
        scope_client = EngineeringOSScopeClient(
            self.os_url,
            token=self.token,
            client=self.client,
        )
        scope = scope_client.ensure(self.workspace, self.user_request)
        binding = store.create(scope)
        if binding.assigned_host.casefold() != self.assigned_host.casefold():
            raise SourceIngressError("new binding did not bind to requested host")
        return scope, binding

    def _get(self, path: str, operation: str) -> dict[str, Any]:
        return _json_object(self.client.get(self.os_url + path), operation)

    def _post(self, path: str, body: dict[str, Any], operation: str) -> dict[str, Any]:
        return _json_object(self.client.post(self.os_url + path, json=body), operation)

    def _materialize_canonical(self, source: Path, target: Path, expected_sha: str) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.stat().st_size <= 0:
                raise SourceIngressError(f"canonical source path is not a non-empty file: {target}")
            actual = sha256_file(target)
            if actual != expected_sha:
                raise SourceIngressError(
                    f"canonical source already exists with different SHA256: {actual}"
                )
            return True
        tmp = target.with_name(target.name + ".tmp")
        try:
            with source.open("rb") as src, tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            if sha256_file(tmp) != expected_sha:
                raise SourceIngressError("temporary canonical source SHA256 changed during copy")
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                tmp.unlink()
        return False

    def _ensure_os_input(
        self,
        *,
        scope: EngineeringScope,
        source: Path,
        original_name: str,
        media_type: str,
        size: int,
        digest: str,
    ) -> tuple[dict[str, Any], bool]:
        listed = self._get(f"/api/v1/jobs/{scope.job_id}/inputs", "list job inputs")
        items = listed.get("items")
        if not isinstance(items, list):
            raise SourceIngressError("OS job input list has no items array")
        same = [
            item for item in items
            if isinstance(item, dict)
            and str(item.get("original_name") or "") == original_name
            and int(item.get("size") or -1) == size
            and str(item.get("sha256") or "").casefold() == digest.casefold()
        ]
        if len(same) > 1:
            raise SourceIngressError("multiple identical OS Job Inputs already exist")
        if same:
            return same[0], True
        payload = {
            "file_name": original_name,
            "media_type": media_type,
            "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        }
        imported = self._post(
            f"/api/v1/jobs/{scope.job_id}/inputs",
            payload,
            "import job input",
        )
        if int(imported.get("size") or -1) != size:
            raise SourceIngressError("OS imported input size does not match source")
        if str(imported.get("sha256") or "").casefold() != digest.casefold():
            raise SourceIngressError("OS imported input SHA256 does not match source")
        return imported, False

    def _ensure_source_artifact(
        self,
        *,
        scope: EngineeringScope,
        os_input: dict[str, Any],
        media_type: str,
        digest: str,
        source_run_id: str,
        producer_repository: str,
        producer_commit_sha: str,
    ) -> tuple[dict[str, Any], bool]:
        job = self._get(f"/api/v1/jobs/{scope.job_id}", "get job")
        working_dir = Path(str(job.get("working_dir") or "")).resolve()
        if not str(working_dir):
            raise SourceIngressError("OS job has no working_dir")
        rel = str(os_input.get("relative_path") or "").strip()
        if not rel:
            raise SourceIngressError("OS input has no relative_path")
        os_input_path = (working_dir.parent / Path(rel.replace("/", os.sep))).resolve()
        try:
            os_input_path.relative_to(working_dir.parent)
        except ValueError as exc:
            raise SourceIngressError("OS input path escapes job root") from exc
        if not os_input_path.is_file():
            raise SourceIngressError(f"OS input physical file missing: {os_input_path}")
        if sha256_file(os_input_path) != digest:
            raise SourceIngressError("OS input physical file SHA256 mismatch")

        listed = self._get(
            f"/api/v1/projects/{scope.project_id}/artifacts",
            "list project artifacts",
        )
        items = listed.get("items")
        if not isinstance(items, list):
            raise SourceIngressError("OS artifact list has no items array")
        matches = [
            item for item in items
            if isinstance(item, dict)
            and str(item.get("job_id") or "") == scope.job_id
            and str(item.get("component_id") or "") == "source"
            and str(item.get("kind") or "") == "source-dwg"
            and str(item.get("checksum") or "").casefold() == f"sha256:{digest}".casefold()
        ]
        if len(matches) > 1:
            latest = max(matches, key=lambda item: int(item.get("revision") or 0))
            return latest, True
        if matches:
            return matches[0], True
        body: dict[str, Any] = {
            "job_id": scope.job_id,
            "component_id": "source",
            "kind": "source-dwg",
            "uri": str(os_input_path),
            "media_type": media_type,
            "checksum": f"sha256:{digest}",
            "source_run_id": source_run_id,
        }
        if producer_repository and producer_commit_sha:
            body["producer_repository"] = producer_repository
            body["producer_commit_sha"] = producer_commit_sha
        artifact = self._post(
            f"/api/v1/projects/{scope.project_id}/artifacts",
            body,
            "register source artifact",
        )
        return artifact, False

    def ingest(
        self,
        source_path: str | os.PathLike[str],
        *,
        canonical_name: str = "source.dwg",
        original_name: str = "",
        media_type: str = "application/acad",
        expected_size: int | None = None,
        expected_sha256: str = "",
        expected_header: str = "",
        source_run_id: str = "",
        producer_repository: str = "",
        producer_commit_sha: str = "",
    ) -> SourceIngressResult:
        actual_host = self._host_gate()
        source = Path(source_path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise SourceIngressError(f"source is missing or empty: {source}")
        size = source.stat().st_size
        digest = sha256_file(source)
        expected_digest = str(expected_sha256 or "").strip().lower()
        if expected_size is not None and size != int(expected_size):
            raise SourceIngressError(f"source size mismatch: expected {expected_size}, got {size}")
        if expected_digest and digest != expected_digest:
            raise SourceIngressError(f"source SHA256 mismatch: expected {expected_digest}, got {digest}")
        header_bytes = source.read_bytes()[:32]
        header = header_bytes.decode("ascii", errors="replace").rstrip("\x00")
        expected_head = str(expected_header or "").strip()
        if expected_head and not header.startswith(expected_head):
            raise SourceIngressError(f"source header mismatch: expected prefix {expected_head!r}, got {header!r}")

        safe_name = _safe_leaf(canonical_name, fallback="source.bin")
        original = _safe_leaf(original_name or source.name, fallback=source.name)
        scope, binding = self._scope_and_binding()
        canonical = (self.workspace / "input" / safe_name).resolve()
        try:
            canonical.relative_to(self.workspace)
        except ValueError as exc:
            raise SourceIngressError("canonical source path escapes workspace") from exc
        already_materialized = self._materialize_canonical(source, canonical, digest)

        os_input, already_imported = self._ensure_os_input(
            scope=scope,
            source=canonical,
            original_name=original,
            media_type=media_type,
            size=size,
            digest=digest,
        )
        artifact, already_registered = self._ensure_source_artifact(
            scope=scope,
            os_input=os_input,
            media_type=media_type,
            digest=digest,
            source_run_id=str(source_run_id or "").strip(),
            producer_repository=str(producer_repository or "").strip(),
            producer_commit_sha=str(producer_commit_sha or "").strip(),
        )

        result = SourceIngressResult(
            schema_version="openworker.engineering-source-ingress.v1",
            project_id=scope.project_id,
            project_code=scope.project_code,
            job_id=scope.job_id,
            job_code=scope.job_code,
            assigned_host=actual_host,
            workspace_root=str(self.workspace),
            canonical_path=str(canonical),
            original_name=original,
            media_type=media_type,
            size=size,
            sha256=digest,
            header=header,
            os_input_id=str(os_input.get("id") or ""),
            os_input_relative_path=str(os_input.get("relative_path") or ""),
            os_artifact_id=str(artifact.get("id") or ""),
            os_artifact_revision=int(artifact.get("revision") or 0),
            already_materialized=already_materialized,
            already_imported=already_imported,
            already_registered=already_registered,
        )
        provenance_path = self.workspace / "input" / "source-provenance.json"
        tmp = provenance_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, provenance_path)

        ProjectKnowledgeStore(self.workspace).record(
            kind="accepted",
            stage="source-ingress",
            summary=f"Accepted immutable engineering source {original}",
            status="PASS",
            owner="openworker",
            capability_id="engineering.source.ingress",
            evidence=(str(canonical), str(provenance_path), result.os_artifact_id),
            decisions=(f"assigned_host={actual_host}", f"sha256={digest}"),
            next_actions=("Query go-tool-runtime for the next product capability.",),
            details=result.as_dict(),
            execution_id=str(source_run_id or ""),
            artifact_refs=(result.os_artifact_id,),
            artifact_disposition="accepted",
        )
        return result


__all__ = [
    "EngineeringSourceIngress",
    "SourceIngressError",
    "SourceIngressResult",
    "sha256_file",
]
