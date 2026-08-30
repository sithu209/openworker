"""Traceable Google Drive publication for OpenWorker LLM review bundles.

The local workspace and WorkLedger remain authoritative.  This module only publishes
immutable review evidence to a bounded Google Drive folder and returns cloud identities
that can be recorded back into the ledger.  Credentials and bearer tokens are never
written into receipts.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

import httpx

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
DEFAULT_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
PUBLISH_RECEIPT_NAME = "review-publish-receipt.json"


class ReviewDriveError(RuntimeError):
    """Fail-closed Google Drive publication error."""


@dataclass(frozen=True)
class DrivePublishedFile:
    relative_path: str
    sha256: str
    size_bytes: int
    mime_type: str
    drive_file_id: str
    web_view_link: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "drive_file_id": self.drive_file_id,
            "web_view_link": self.web_view_link,
        }


@dataclass(frozen=True)
class ReviewPublishReceipt:
    revision_id: str
    work_code: str
    machine_id: str
    drive_root_folder_id: str
    drive_revision_folder_id: str
    drive_revision_web_view_link: str
    bundle_manifest_sha256: str
    published_at: str
    files: tuple[DrivePublishedFile, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "openworker-review-publish-receipt/v1",
            "transport": "google-drive-api",
            "status": "WAITING_LLM_REVIEW",
            "revision_id": self.revision_id,
            "work_code": self.work_code,
            "machine_id": self.machine_id,
            "drive_root_folder_id": self.drive_root_folder_id,
            "drive_revision_folder_id": self.drive_revision_folder_id,
            "drive_revision_web_view_link": self.drive_revision_web_view_link,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "published_at": self.published_at,
            "files": [item.to_dict() for item in self.files],
            "metadata": dict(self.metadata),
        }


class ReviewDriveUploader(Protocol):
    def ensure_folder(
        self,
        *,
        name: str,
        parent_id: str,
        app_properties: Mapping[str, str],
    ) -> Mapping[str, Any]: ...

    def upload_file(
        self,
        *,
        path: Path,
        name: str,
        parent_id: str,
        sha256: str,
        mime_type: str,
        app_properties: Mapping[str, str],
    ) -> Mapping[str, Any]: ...


class _GoogleAuthResponse:
    def __init__(self, response: httpx.Response) -> None:
        self.status = response.status_code
        self.data = response.content
        self.headers = response.headers


class _GoogleAuthHttpxRequest:
    """Small google-auth Request adapter backed by the project's existing httpx."""

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = 120,
        **_: Any,
    ) -> _GoogleAuthResponse:
        response = httpx.request(method, url, content=body, headers=headers, timeout=timeout)
        return _GoogleAuthResponse(response)


class GoogleDriveAPIClient:
    """Minimal Drive v3 client with resumable uploads and SHA-based idempotency."""

    def __init__(
        self,
        *,
        access_token: str | None = None,
        credentials: Any | None = None,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        token = str(access_token or "").strip()
        if not token and credentials is None:
            raise ReviewDriveError("Google Drive credentials unavailable")
        self._access_token = token
        self._credentials = credentials
        self.timeout_seconds = float(timeout_seconds)
        self._client = client or httpx.Client(timeout=self.timeout_seconds)

    @classmethod
    def from_environment(cls) -> "GoogleDriveAPIClient":
        token = str(os.environ.get("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN") or "").strip()
        if token:
            return cls(access_token=token)
        try:
            import google.auth

            scope = str(os.environ.get("OPENWORKER_GOOGLE_DRIVE_SCOPE") or DEFAULT_DRIVE_SCOPE).strip()
            credentials, _project = google.auth.default(scopes=[scope])
        except Exception as exc:  # pragma: no cover - depends on host credential setup
            raise ReviewDriveError(
                "Google Drive API credentials unavailable; configure Application Default Credentials "
                "or OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN"
            ) from exc
        return cls(credentials=credentials)

    def close(self) -> None:
        self._client.close()

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        credentials = self._credentials
        if credentials is None:
            raise ReviewDriveError("Google Drive credentials unavailable")
        try:
            if not getattr(credentials, "valid", False) or not getattr(credentials, "token", None):
                credentials.refresh(_GoogleAuthHttpxRequest())
        except Exception as exc:
            raise ReviewDriveError(f"Google Drive credential refresh failed: {exc}") from exc
        token = str(getattr(credentials, "token", "") or "").strip()
        if not token:
            raise ReviewDriveError("Google Drive credential refresh returned no access token")
        return token

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token()}"}
        if extra:
            headers.update({str(k): str(v) for k, v in extra.items()})
        return headers

    def _json_request(self, method: str, url: str, **kwargs: Any) -> Mapping[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        response = self._client.request(method, url, headers=self._headers(headers), **kwargs)
        if response.status_code >= 400:
            detail = response.text[:1000].replace("\n", " ")
            raise ReviewDriveError(f"Google Drive API {method} failed HTTP {response.status_code}: {detail}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ReviewDriveError("Google Drive API returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ReviewDriveError("Google Drive API returned non-object JSON")
        return payload

    def _find_named(self, *, name: str, parent_id: str, folder: bool) -> list[Mapping[str, Any]]:
        escaped_name = _drive_query_quote(name)
        escaped_parent = _drive_query_quote(parent_id)
        clauses = [f"name = '{escaped_name}'", f"'{escaped_parent}' in parents", "trashed = false"]
        if folder:
            clauses.append("mimeType = 'application/vnd.google-apps.folder'")
        payload = self._json_request(
            "GET",
            f"{DRIVE_API_BASE}/files",
            params={
                "q": " and ".join(clauses),
                "fields": "files(id,name,mimeType,size,webViewLink,appProperties)",
                "pageSize": "10",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        files = payload.get("files") or []
        if not isinstance(files, list):
            raise ReviewDriveError("Google Drive files query returned invalid files list")
        return [item for item in files if isinstance(item, Mapping)]

    def ensure_folder(
        self,
        *,
        name: str,
        parent_id: str,
        app_properties: Mapping[str, str],
    ) -> Mapping[str, Any]:
        name = _required_text(name, "Drive folder name")
        parent_id = _required_text(parent_id, "Drive parent folder id")
        matches = self._find_named(name=name, parent_id=parent_id, folder=True)
        if len(matches) > 1:
            raise ReviewDriveError(f"ambiguous Google Drive folder {name!r} under parent {parent_id}")
        if matches:
            return _require_drive_identity(matches[0], context=f"folder {name}")
        payload = self._json_request(
            "POST",
            f"{DRIVE_API_BASE}/files",
            params={"fields": "id,name,webViewLink,appProperties", "supportsAllDrives": "true"},
            json={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
                "appProperties": dict(app_properties),
            },
        )
        return _require_drive_identity(payload, context=f"created folder {name}")

    def upload_file(
        self,
        *,
        path: Path,
        name: str,
        parent_id: str,
        sha256: str,
        mime_type: str,
        app_properties: Mapping[str, str],
    ) -> Mapping[str, Any]:
        source = Path(path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise ReviewDriveError(f"Google Drive upload source missing/empty: {source}")
        name = _required_text(name, "Drive file name")
        parent_id = _required_text(parent_id, "Drive parent folder id")
        digest = _required_text(sha256, "Drive file sha256")
        matches = self._find_named(name=name, parent_id=parent_id, folder=False)
        if len(matches) > 1:
            raise ReviewDriveError(f"ambiguous Google Drive file {name!r} under parent {parent_id}")
        if matches:
            existing = matches[0]
            props = existing.get("appProperties") or {}
            existing_sha = str(props.get("openworkerSha256") or "") if isinstance(props, Mapping) else ""
            if existing_sha != digest:
                raise ReviewDriveError(
                    f"Google Drive immutable publish conflict for {name}: existing SHA {existing_sha!r} != {digest}"
                )
            return _require_drive_identity(existing, context=f"existing file {name}")

        size = source.stat().st_size
        properties = {str(k): str(v) for k, v in app_properties.items()}
        properties["openworkerSha256"] = digest
        start = self._client.post(
            f"{DRIVE_UPLOAD_BASE}/files",
            params={
                "uploadType": "resumable",
                "fields": "id,name,mimeType,size,webViewLink,appProperties",
                "supportsAllDrives": "true",
            },
            headers=self._headers(
                {
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": mime_type,
                    "X-Upload-Content-Length": str(size),
                }
            ),
            json={"name": name, "parents": [parent_id], "appProperties": properties},
        )
        if start.status_code >= 400:
            raise ReviewDriveError(
                f"Google Drive resumable upload start failed HTTP {start.status_code}: {start.text[:1000]}"
            )
        upload_url = str(start.headers.get("Location") or "").strip()
        if not upload_url:
            raise ReviewDriveError("Google Drive resumable upload returned no Location header")
        with source.open("rb") as fh:
            finish = self._client.put(
                upload_url,
                headers={"Content-Type": mime_type, "Content-Length": str(size)},
                content=fh,
            )
        if finish.status_code >= 400:
            raise ReviewDriveError(
                f"Google Drive resumable upload failed HTTP {finish.status_code}: {finish.text[:1000]}"
            )
        try:
            payload = finish.json()
        except ValueError as exc:
            raise ReviewDriveError("Google Drive upload returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ReviewDriveError("Google Drive upload returned non-object JSON")
        identity = _require_drive_identity(payload, context=f"uploaded file {name}")
        returned_size = identity.get("size")
        if returned_size not in (None, "") and int(returned_size) != size:
            raise ReviewDriveError(f"Google Drive uploaded size mismatch for {name}: {returned_size} != {size}")
        return identity


def publish_review_bundle(
    bundle_root: str | Path,
    *,
    work_code: str,
    root_folder_id: str,
    uploader: ReviewDriveUploader,
    machine_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> ReviewPublishReceipt:
    """Publish one immutable bundle and write/upload a final cloud-identity receipt.

    Every pre-existing cloud file must carry the same OpenWorker SHA or publication
    fails.  This makes interrupted publication safely resumable without allowing a
    different artifact to silently replace the revision under review.
    """
    source = Path(bundle_root).expanduser().resolve()
    if not source.is_dir():
        raise ReviewDriveError(f"review bundle unavailable: {source}")
    revision_id = _required_text(source.name, "revision id")
    work_code = _required_text(work_code, "work code")
    root_folder_id = _required_text(root_folder_id, "Drive root folder id")
    machine_id = _required_text(machine_id, "machine id")
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise ReviewDriveError(f"review bundle manifest missing: {manifest_path}")
    manifest_sha = _sha256(manifest_path)

    common_props = {
        "openworkerRevisionId": revision_id,
        "openworkerWorkCode": work_code,
    }
    work_folder = uploader.ensure_folder(
        name=_safe_drive_name(work_code),
        parent_id=root_folder_id,
        app_properties={**common_props, "openworkerKind": "work"},
    )
    work_folder_id = _identity_id(work_folder, "work folder")
    revision_folder = uploader.ensure_folder(
        name=_safe_drive_name(revision_id),
        parent_id=work_folder_id,
        app_properties={**common_props, "openworkerKind": "review-revision"},
    )
    revision_folder_id = _identity_id(revision_folder, "revision folder")
    revision_link = _identity_link(revision_folder, "revision folder")

    folder_ids: dict[PurePosixPath, str] = {PurePosixPath("."): revision_folder_id}
    published: list[DrivePublishedFile] = []
    files = sorted(
        (path for path in source.rglob("*") if path.is_file() and path.name != PUBLISH_RECEIPT_NAME),
        key=lambda path: path.relative_to(source).as_posix(),
    )
    if not files:
        raise ReviewDriveError("review bundle contains no publishable files")

    for path in files:
        rel = PurePosixPath(path.relative_to(source).as_posix())
        parent_rel = rel.parent
        parent_id = _ensure_relative_folder_tree(
            uploader,
            parent_rel=parent_rel,
            folder_ids=folder_ids,
            revision_folder_id=revision_folder_id,
            common_props=common_props,
        )
        digest = _sha256(path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        identity = uploader.upload_file(
            path=path,
            name=path.name,
            parent_id=parent_id,
            sha256=digest,
            mime_type=mime_type,
            app_properties={**common_props, "openworkerRelativePath": rel.as_posix()},
        )
        published.append(
            DrivePublishedFile(
                relative_path=rel.as_posix(),
                sha256=digest,
                size_bytes=path.stat().st_size,
                mime_type=mime_type,
                drive_file_id=_identity_id(identity, rel.as_posix()),
                web_view_link=_identity_link(identity, rel.as_posix()),
            )
        )

    receipt = ReviewPublishReceipt(
        revision_id=revision_id,
        work_code=work_code,
        machine_id=machine_id,
        drive_root_folder_id=root_folder_id,
        drive_revision_folder_id=revision_folder_id,
        drive_revision_web_view_link=revision_link,
        bundle_manifest_sha256=manifest_sha,
        published_at=datetime.now(timezone.utc).isoformat(),
        files=tuple(published),
        metadata=dict(metadata or {}),
    )
    receipt_path = source / PUBLISH_RECEIPT_NAME
    receipt_path.write_text(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    receipt_sha = _sha256(receipt_path)
    uploader.upload_file(
        path=receipt_path,
        name=PUBLISH_RECEIPT_NAME,
        parent_id=revision_folder_id,
        sha256=receipt_sha,
        mime_type="application/json",
        app_properties={**common_props, "openworkerKind": "publish-receipt"},
    )
    return receipt


def _ensure_relative_folder_tree(
    uploader: ReviewDriveUploader,
    *,
    parent_rel: PurePosixPath,
    folder_ids: dict[PurePosixPath, str],
    revision_folder_id: str,
    common_props: Mapping[str, str],
) -> str:
    if parent_rel in (PurePosixPath("."), PurePosixPath("")):
        return revision_folder_id
    current = PurePosixPath(".")
    current_id = revision_folder_id
    for part in parent_rel.parts:
        if part in ("", "."):
            continue
        current = PurePosixPath(part) if current == PurePosixPath(".") else current / part
        if current in folder_ids:
            current_id = folder_ids[current]
            continue
        identity = uploader.ensure_folder(
            name=_safe_drive_name(part),
            parent_id=current_id,
            app_properties={**common_props, "openworkerRelativeDir": current.as_posix()},
        )
        current_id = _identity_id(identity, f"folder {current.as_posix()}")
        folder_ids[current] = current_id
    return current_id


def _require_drive_identity(payload: Mapping[str, Any], *, context: str) -> Mapping[str, Any]:
    _identity_id(payload, context)
    _identity_link(payload, context)
    return payload


def _identity_id(payload: Mapping[str, Any], context: str) -> str:
    return _required_text(payload.get("id"), f"Google Drive {context} id")


def _identity_link(payload: Mapping[str, Any], context: str) -> str:
    value = str(payload.get("webViewLink") or "").strip()
    if value:
        return value
    item_id = _identity_id(payload, context)
    return f"https://drive.google.com/open?id={item_id}"


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ReviewDriveError(f"{label} must not be empty")
    return text


def _safe_drive_name(value: str) -> str:
    text = _required_text(value, "Drive name").replace("/", "-").replace("\\", "-")
    text = text.strip().strip(".")
    if not text:
        raise ReviewDriveError("Drive name is empty after normalization")
    return text[:180]


def _drive_query_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_DRIVE_SCOPE",
    "DrivePublishedFile",
    "GoogleDriveAPIClient",
    "PUBLISH_RECEIPT_NAME",
    "ReviewDriveError",
    "ReviewDriveUploader",
    "ReviewPublishReceipt",
    "publish_review_bundle",
]
