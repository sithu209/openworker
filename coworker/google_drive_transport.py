"""Google Drive API transport for OpenWorker local artifact review exchange."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_DRIVE_FOLDER_ID = "1A4BnZEcFe2WIhcperRd4QSpxoSUN_ARR"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


class GoogleDriveTransportError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    data: bytes | None = None,
) -> dict[str, Any]:
    req = urllib.request.Request(url, method=method, headers=dict(headers or {}), data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GoogleDriveTransportError(f"Google API HTTP {exc.code}: {body[:800]}") from exc
    except urllib.error.URLError as exc:
        raise GoogleDriveTransportError(f"Google API unavailable: {exc}") from exc
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise GoogleDriveTransportError("Google API returned invalid JSON") from exc


@dataclass(frozen=True)
class DriveCredentials:
    access_token: str
    source: str

    @classmethod
    def resolve(cls) -> "DriveCredentials":
        direct = os.environ.get("OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN", "").strip()
        if direct:
            return cls(access_token=direct, source="access_token_env")

        client_id = os.environ.get("OPENWORKER_GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.environ.get("OPENWORKER_GOOGLE_CLIENT_SECRET", "").strip()
        refresh_token = os.environ.get("OPENWORKER_GOOGLE_REFRESH_TOKEN", "").strip()

        credential_file = os.environ.get("OPENWORKER_GOOGLE_CREDENTIALS_FILE", "").strip()
        if credential_file:
            path = Path(credential_file).expanduser().resolve()
            if not path.is_file():
                raise GoogleDriveTransportError(f"Google credential file unavailable: {path}")
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise GoogleDriveTransportError(f"invalid Google credential file: {path}") from exc
            if payload.get("type") not in (None, "authorized_user"):
                raise GoogleDriveTransportError("V1 supports only authorized_user Google credential files")
            client_id = client_id or str(payload.get("client_id") or "").strip()
            client_secret = client_secret or str(payload.get("client_secret") or "").strip()
            refresh_token = refresh_token or str(payload.get("refresh_token") or "").strip()

        if not (client_id and client_secret and refresh_token):
            raise GoogleDriveTransportError(
                "Google Drive credentials missing; set OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN or "
                "OPENWORKER_GOOGLE_CLIENT_ID/OPENWORKER_GOOGLE_CLIENT_SECRET/OPENWORKER_GOOGLE_REFRESH_TOKEN "
                "or OPENWORKER_GOOGLE_CREDENTIALS_FILE"
            )
        body = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        result = _json_request(
            TOKEN_ENDPOINT,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=body,
        )
        token = str(result.get("access_token") or "").strip()
        if not token:
            raise GoogleDriveTransportError("Google OAuth refresh returned no access_token")
        return cls(access_token=token, source="oauth_refresh")


class GoogleDriveTransport:
    def __init__(self, credentials: DriveCredentials | None = None) -> None:
        self.credentials = credentials or DriveCredentials.resolve()

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials.access_token}"}

    def auth_check(self) -> dict[str, Any]:
        url = DRIVE_API + "/about?fields=user(displayName,emailAddress),storageQuota(limit,usage)"
        result = _json_request(url, headers=self.headers)
        return {"status": "OK", "credential_source": self.credentials.source, "about": result}

    def upload_file(
        self,
        source: str | Path,
        *,
        folder_id: str = DEFAULT_DRIVE_FOLDER_ID,
        name: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        path = Path(source).expanduser().resolve()
        if not path.is_file() or path.stat().st_size <= 0:
            raise GoogleDriveTransportError(f"upload source missing/empty: {path}")
        size = path.stat().st_size
        digest = sha256_file(path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        metadata: dict[str, Any] = {"name": str(name or path.name)}
        if folder_id.strip():
            metadata["parents"] = [folder_id.strip()]
        if description.strip():
            metadata["description"] = description.strip()

        boundary = "openworker_" + uuid.uuid4().hex
        crlf = b"\r\n"
        prefix = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
            + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = prefix + path.read_bytes() + suffix
        fields = "id,name,mimeType,size,md5Checksum,webViewLink,parents,createdTime"
        url = DRIVE_UPLOAD_API + "/files?uploadType=multipart&fields=" + urllib.parse.quote(fields, safe=",")
        headers = dict(self.headers)
        headers["Content-Type"] = f"multipart/related; boundary={boundary}"
        result = _json_request(url, method="POST", headers=headers, data=body)
        file_id = str(result.get("id") or "").strip()
        if not file_id:
            raise GoogleDriveTransportError("Google Drive upload returned no file id")
        remote_size = result.get("size")
        if remote_size not in (None, "") and int(remote_size) != size:
            raise GoogleDriveTransportError(f"Drive size mismatch local={size} remote={remote_size}")
        return {
            "source_path": str(path),
            "source_sha256": digest,
            "source_size": size,
            "drive_file_id": file_id,
            "drive_name": result.get("name") or metadata["name"],
            "drive_mime_type": result.get("mimeType") or mime,
            "drive_size": result.get("size"),
            "drive_md5_checksum": result.get("md5Checksum"),
            "drive_web_view_link": result.get("webViewLink"),
            "drive_parent_ids": result.get("parents") or metadata.get("parents") or [],
            "drive_created_time": result.get("createdTime"),
        }

    def list_files(self, *, folder_id: str = DEFAULT_DRIVE_FOLDER_ID, name: str = "") -> dict[str, Any]:
        clauses = ["trashed = false"]
        if folder_id.strip():
            clauses.append(f"'{folder_id.strip()}' in parents")
        if name.strip():
            safe = name.replace("'", "\\'")
            clauses.append(f"name contains '{safe}'")
        params = urllib.parse.urlencode(
            {
                "q": " and ".join(clauses),
                "fields": "files(id,name,mimeType,size,md5Checksum,webViewLink,parents,createdTime,modifiedTime)",
                "pageSize": "100",
                "orderBy": "modifiedTime desc",
            }
        )
        return _json_request(DRIVE_API + "/files?" + params, headers=self.headers)

    def download_file(self, file_id: str, output: str | Path) -> dict[str, Any]:
        fid = str(file_id).strip()
        if not fid:
            raise GoogleDriveTransportError("file_id is required")
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(DRIVE_API + f"/files/{urllib.parse.quote(fid)}?alt=media", headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GoogleDriveTransportError(f"Google Drive download HTTP {exc.code}: {body[:800]}") from exc
        if not data:
            raise GoogleDriveTransportError("Google Drive download returned empty content")
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        return {"file_id": fid, "output_path": str(target), "size": target.stat().st_size, "sha256": sha256_file(target)}


def write_receipt(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(payload)
    forbidden = {"access_token", "refresh_token", "client_secret", "authorization"}
    for key in list(normalized):
        if key.lower() in forbidden:
            normalized.pop(key, None)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def deterministic_zip(source_dir: str | Path) -> Path:
    root = Path(source_dir).expanduser().resolve()
    if not root.is_dir():
        raise GoogleDriveTransportError(f"review source directory unavailable: {root}")
    files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix().casefold())
    if not files:
        raise GoogleDriveTransportError(f"review source directory has no files: {root}")
    fd, temp_name = tempfile.mkstemp(prefix="openworker-drive-", suffix=".zip")
    os.close(fd)
    target = Path(temp_name)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return target


def build_upload_receipt(upload: Mapping[str, Any], *, status: str = "UPLOADED") -> dict[str, Any]:
    return {
        "schema": "openworker.google-drive-upload-receipt.v1",
        "status": status,
        **dict(upload),
        "openworker_job_id": os.environ.get("OPENWORKER_JOB_ID", ""),
        "openworker_agent_slot": os.environ.get("OPENWORKER_AGENT_SLOT", ""),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "DEFAULT_DRIVE_FOLDER_ID",
    "DriveCredentials",
    "GoogleDriveTransport",
    "GoogleDriveTransportError",
    "build_upload_receipt",
    "deterministic_zip",
    "sha256_file",
    "write_receipt",
]
