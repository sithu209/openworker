"""Local-only tool-context ingress used by the OpenWorker Harness Cordis plugin.

ACP rc.5 permission requests carry only a tool call id. The Harness plugin sees
the actual call name and arguments before returning `ask`, so it posts those
facts to this loopback-only ingress. OpenWorker does *not* trust plugin-supplied
canonical ids, side-effect labels, or risk metadata: HarnessEngineeringToolGateway
resolves the exposed name against OpenWorker's own dynamically discovered
AI-Engineering-OS catalog and creates the authoritative H4 context.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .harness_engineering_tools import (
    EngineeringOSToolDiscoveryError,
    HarnessEngineeringToolGateway,
)

_CONTEXT_PATH = "/v1/harness/tool-context"
_HEALTH_PATH = "/healthz"
_MAX_BODY_BYTES = 1 << 20


class HarnessContextIngressError(RuntimeError):
    """Raised when the loopback ingress cannot be created safely."""


@dataclass(frozen=True)
class HarnessContextIngressAddress:
    host: str
    port: int
    token: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class HarnessContextIngressServer:
    """Small authenticated loopback HTTP bridge for H6.1 tool context.

    The server intentionally binds only 127.0.0.1 and generates a high-entropy
    bearer token when the caller does not provide one. It accepts only the
    minimum facts the plugin actually knows: callId, exposed tool name and
    arguments. Canonical OS metadata is resolved inside OpenWorker.
    """

    def __init__(
        self,
        gateway: HarnessEngineeringToolGateway,
        *,
        token: str | None = None,
        port: int = 0,
        max_body_bytes: int = _MAX_BODY_BYTES,
    ) -> None:
        self.gateway = gateway
        self.token = token or secrets.token_urlsafe(32)
        if not self.token:
            raise HarnessContextIngressError("context ingress token must not be empty")
        self.max_body_bytes = int(max_body_bytes)
        if self.max_body_bytes <= 0:
            raise HarnessContextIngressError("max_body_bytes must be positive")
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "OpenWorkerHarnessContext/1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            def _content_length(self) -> int:
                value = self.headers.get("Content-Length")
                try:
                    return int(value or "0")
                except ValueError:
                    return -1

            def _discard_bounded_body(self) -> None:
                """Drain a small rejected request body before closing the socket.

                Windows can surface an unread request body as WSAECONNABORTED/
                WinError 10053 to the client even after the handler wrote a valid
                HTTP error response. Draining only bounded Content-Length bytes
                preserves auth-before-parse while making rejection deterministic.
                """

                remaining = self._content_length()
                if remaining <= 0 or remaining > owner.max_body_bytes:
                    return
                while remaining:
                    chunk = self.rfile.read(min(remaining, 64 * 1024))
                    if not chunk:
                        return
                    remaining -= len(chunk)

            def _authorized(self) -> bool:
                header = self.headers.get("Authorization", "")
                prefix = "Bearer "
                supplied = header[len(prefix) :] if header.startswith(prefix) else ""
                return bool(supplied) and hmac.compare_digest(supplied, owner.token)

            def do_GET(self) -> None:  # noqa: N802
                if self.path != _HEALTH_PATH:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                self._json(HTTPStatus.OK, {"status": "ok"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != _CONTEXT_PATH:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                if not self._authorized():
                    self._discard_bounded_body()
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                length = self._content_length()
                if length < 0 or length > owner.max_body_bytes:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_too_large"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                    return
                if not isinstance(payload, dict):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
                    return
                call_id = payload.get("callId")
                name = payload.get("name")
                arguments = payload.get("arguments")
                if (
                    not isinstance(call_id, str)
                    or not call_id.strip()
                    or not isinstance(name, str)
                    or not name.strip()
                    or not isinstance(arguments, dict)
                ):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
                    return
                # Reject any attempt to smuggle policy/canonical fields. The ingress owns
                # exactly this three-field vocabulary.
                if set(payload) != {"callId", "name", "arguments"}:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "unexpected_fields"})
                    return
                try:
                    context = owner.gateway.prepare_call(call_id, name, arguments)
                except (ValueError, EngineeringOSToolDiscoveryError) as exc:
                    self._json(
                        HTTPStatus.CONFLICT,
                        {"error": "context_rejected", "message": str(exc)},
                    )
                    return
                canonical = getattr(context.metadata, "canonical_tool_id", "")
                self._json(
                    HTTPStatus.CREATED,
                    {
                        "status": "registered",
                        "callId": context.tool_call_id,
                        "canonicalToolId": canonical,
                    },
                )

            def do_DELETE(self) -> None:  # noqa: N802
                if self.path != _CONTEXT_PATH:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                if not self._authorized():
                    self._discard_bounded_body()
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                length = self._content_length()
                if length < 0 or length > 4096:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_too_large"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                    return
                call_id = payload.get("callId") if isinstance(payload, dict) else None
                if not isinstance(call_id, str) or set(payload) != {"callId"}:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
                    return
                owner.gateway.finish_call(call_id)
                self._json(HTTPStatus.OK, {"status": "discarded", "callId": call_id})

        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
        except OSError as exc:
            raise HarnessContextIngressError(f"failed to bind loopback context ingress: {exc}") from exc
        self._thread: Optional[threading.Thread] = None

    @property
    def address(self) -> HarnessContextIngressAddress:
        host, port = self._httpd.server_address[:2]
        return HarnessContextIngressAddress(str(host), int(port), self.token)

    def start(self) -> HarnessContextIngressAddress:
        if self._thread is not None and self._thread.is_alive():
            return self.address
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="openworker-harness-context-ingress",
            daemon=True,
        )
        self._thread.start()
        return self.address

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "HarnessContextIngressServer":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "HarnessContextIngressAddress",
    "HarnessContextIngressError",
    "HarnessContextIngressServer",
]
