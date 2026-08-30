"""Bounded read-only Google Drive receipt access for review gates.

This is deliberately not a command-ingress client. It can only locate one exact
non-folder file under one already-authoritative parent folder and decode a JSON object.
The receipt may be a raw JSON/text file or a native Google Doc whose plain-text export
contains the same strict JSON schema; this lets ChatGPT write the receipt with its
Drive/Docs connector without introducing an arbitrary binary-upload channel.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .review_drive import DRIVE_API_BASE, GoogleDriveAPIClient, ReviewDriveError, _required_text

_GOOGLE_DOC = "application/vnd.google-apps.document"


class GoogleDriveReviewReceiptClient(GoogleDriveAPIClient):
    def fetch_exact_json(self, *, parent_id: str, name: str, max_bytes: int = 1024 * 1024) -> tuple[Mapping[str, Any], dict[str, Any]] | None:
        parent_id = _required_text(parent_id, "Drive review receipt parent id")
        name = _required_text(name, "Drive review receipt file name")
        if "/" in name or "\\" in name or name in {".", ".."}:
            raise ReviewDriveError("Drive review receipt name must be one file component")
        matches = self._find_named(name=name, parent_id=parent_id, folder=False)
        if not matches:
            return None
        if len(matches) != 1:
            raise ReviewDriveError(f"ambiguous Drive review receipt {name!r} under {parent_id}")
        identity = matches[0]
        file_id = str(identity.get("id") or "").strip()
        if not file_id:
            raise ReviewDriveError("Drive review receipt has no file id")
        mime_type = str(identity.get("mimeType") or "").strip()
        if mime_type == _GOOGLE_DOC:
            response = self._client.get(
                f"{DRIVE_API_BASE}/files/{file_id}/export",
                params={"mimeType": "text/plain"},
                headers=self._headers(),
            )
        else:
            response = self._client.get(
                f"{DRIVE_API_BASE}/files/{file_id}",
                params={"alt": "media", "supportsAllDrives": "true"},
                headers=self._headers(),
            )
        if response.status_code >= 400:
            raise ReviewDriveError(f"Drive review receipt download failed HTTP {response.status_code}: {response.text[:500]}")
        body = response.content
        if not body or len(body) > max_bytes:
            raise ReviewDriveError(f"Drive review receipt size is invalid: {len(body)} bytes")
        try:
            value = json.loads(body.decode("utf-8-sig").strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReviewDriveError("Drive review receipt is not valid UTF-8 JSON text") from exc
        if not isinstance(value, dict):
            raise ReviewDriveError("Drive review receipt root must be a JSON object")
        return identity, value
