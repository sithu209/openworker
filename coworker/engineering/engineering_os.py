"""Typed bridge from OpenWorker to the AI-Engineering-OS control plane.

The bridge owns transport/API-contract concerns only. Project, Job, Artifact, Review and
Delivery business rules remain authoritative in AI-Engineering-OS.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Mapping, Protocol
from urllib import error as urlerror
from urllib import request as urlrequest

from .adapters import EngineeringCapability
from .contracts import HealthReport, HealthStatus


class EngineeringOSError(RuntimeError): pass
class EngineeringOSTransportError(EngineeringOSError): pass
class EngineeringOSTimeoutError(EngineeringOSTransportError): pass
class EngineeringOSContractError(EngineeringOSError): pass


class EngineeringOSHTTPError(EngineeringOSError):
    def __init__(self, status: int, code: str | None = None, message: str | None = None):
        self.status, self.code, self.remote_message = status, code, message
        detail = f"AI-Engineering-OS HTTP {status}"
        if code: detail += f" ({code})"
        if message: detail += f": {message}"
        super().__init__(detail)


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes


class EngineeringOSTransport(Protocol):
    def request(self, method: str, url: str, *, body: bytes | None,
                headers: Mapping[str, str], timeout: float) -> TransportResponse: ...


class UrllibEngineeringOSTransport:
    def request(self, method: str, url: str, *, body: bytes | None,
                headers: Mapping[str, str], timeout: float) -> TransportResponse:
        req = urlrequest.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlrequest.urlopen(req, timeout=timeout) as response:
                return TransportResponse(status=response.status, body=response.read())
        except urlerror.HTTPError as exc:
            return TransportResponse(status=exc.code, body=exc.read())
        except (TimeoutError, socket.timeout) as exc:
            raise EngineeringOSTimeoutError(f"AI-Engineering-OS request timed out: {url}") from exc
        except urlerror.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise EngineeringOSTimeoutError(f"AI-Engineering-OS request timed out: {url}") from exc
            raise EngineeringOSTransportError(f"AI-Engineering-OS transport failed: {url}: {exc.reason}") from exc
        except OSError as exc:
            raise EngineeringOSTransportError(f"AI-Engineering-OS transport failed: {url}: {exc}") from exc


@dataclass(frozen=True)
class EngineeringOSConfig:
    base_url: str = "http://127.0.0.1:8080"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("AI-Engineering-OS base_url must use http:// or https://")
        if self.timeout_seconds <= 0:
            raise ValueError("AI-Engineering-OS timeout_seconds must be greater than zero")
        object.__setattr__(self, "base_url", base_url)


_MODULE_CAPABILITIES = {
    "design-engine": {EngineeringCapability.STRUCTURAL, EngineeringCapability.REPORTING},
    "drawing-engine": {EngineeringCapability.DRAWING, EngineeringCapability.REPORTING},
    "bim-engine": {EngineeringCapability.BIM_IFC},
    "quantity-engine": {EngineeringCapability.QUANTITY},
    "budget-engine": {EngineeringCapability.COST},
    "schedule-engine": {EngineeringCapability.SCHEDULING},
    "knowledge-engine": {EngineeringCapability.KNOWLEDGE_GRAPH},
    "visual-workbench": {EngineeringCapability.VISUALIZATION},
    "media-engine": {EngineeringCapability.VISUALIZATION},
}


class EngineeringOSClient:
    def __init__(self, config: EngineeringOSConfig | None = None,
                 *, transport: EngineeringOSTransport | None = None) -> None:
        self.config = config or EngineeringOSConfig()
        self.transport = transport or UrllibEngineeringOSTransport()

    def health(self) -> HealthReport:
        try: payload = self._request_json("GET", "/healthz")
        except EngineeringOSError as exc:
            return HealthReport(status=HealthStatus.UNAVAILABLE, message=str(exc))
        if payload.get("status") != "ok":
            return HealthReport(status=HealthStatus.DEGRADED,
                                message=f"unexpected health status: {payload.get('status')!r}", details=payload)
        return HealthReport(status=HealthStatus.READY, details=payload)

    def readiness(self) -> HealthReport:
        try: payload = self._request_json("GET", "/readyz")
        except EngineeringOSHTTPError as exc:
            if exc.status == 503: return HealthReport(status=HealthStatus.UNAVAILABLE, message=str(exc))
            raise
        except EngineeringOSError as exc:
            return HealthReport(status=HealthStatus.UNAVAILABLE, message=str(exc))
        if payload.get("status") == "ready": return HealthReport(status=HealthStatus.READY, details=payload)
        if payload.get("status") == "not_ready": return HealthReport(status=HealthStatus.UNAVAILABLE, details=payload)
        return HealthReport(status=HealthStatus.DEGRADED,
                            message=f"unexpected readiness status: {payload.get('status')!r}", details=payload)

    def system_modules(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/api/v1/system/modules")
        if not isinstance(payload.get("modules"), list):
            raise EngineeringOSContractError("system/modules response must contain a modules list")
        return payload

    def schema_version(self) -> str | None:
        value = self.system_modules().get("schema_version")
        return value if isinstance(value, str) and value.strip() else None

    def capabilities(self) -> set[EngineeringCapability]:
        caps: set[EngineeringCapability] = set()
        for module in self.system_modules()["modules"]:
            if not isinstance(module, dict):
                raise EngineeringOSContractError("system/modules contains a non-object module")
            if isinstance(module.get("id"), str): caps.update(_MODULE_CAPABILITIES.get(module["id"], set()))
        return caps

    def list_projects(self) -> list[dict[str, Any]]:
        return self._items("/api/v1/projects", "project")

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._object("GET", f"/api/v1/projects/{self._required_id(project_id, 'project_id')}")

    def list_jobs(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        if project_id is None: return self._items("/api/v1/jobs", "job")
        return self._items(f"/api/v1/projects/{self._required_id(project_id, 'project_id')}/jobs", "job")

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._object("GET", f"/api/v1/jobs/{self._required_id(job_id, 'job_id')}")

    def create_job(self, *, project_id: str, code: str, name: str, user_request: str,
                   expected_deliverables: list[str] | None = None, priority: str | None = None,
                   metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": self._required_text(project_id, "project_id"),
            "code": self._required_text(code, "code"),
            "name": self._required_text(name, "name"),
            "user_request": self._required_text(user_request, "user_request"),
        }
        if expected_deliverables is not None: payload["expected_deliverables"] = list(expected_deliverables)
        if priority is not None: payload["priority"] = self._required_text(priority, "priority")
        if metadata is not None: payload["metadata"] = dict(metadata)
        return self._object("POST", "/api/v1/jobs", payload)

    def transition_job(self, *, job_id: str, target: str, expected_revision: int) -> dict[str, Any]:
        job_id = self._required_id(job_id, "job_id")
        target = self._required_text(target, "target")
        if expected_revision < 1: raise ValueError("expected_revision must be >= 1")
        return self._object("POST", f"/api/v1/jobs/{job_id}/transitions",
                            {"target": target, "expected_revision": expected_revision})

    def start_source_to_film(self, *, job_id: str, source_id: str | None = None,
                             language: str | None = None, target_duration_sec: int = 20,
                             default_shot_seconds: int = 5,
                             visual_style: list[str] | None = None,
                             world_rules: list[str] | None = None,
                             acceleration_profile: str = "lightx2v-h3-4step",
                             width: int = 1280, height: int = 720) -> dict[str, Any]:
        """Ask AI-Engineering-OS to start its authoritative source-to-film flow.

        OpenWorker never calls Comfyx-Studio or ComfyX directly here. The OS Job is
        the authority and OS owns the Studio adapter/provenance registration.
        """
        job_id = self._required_id(job_id, "job_id")
        if target_duration_sec <= 0: raise ValueError("target_duration_sec must be > 0")
        if default_shot_seconds <= 0: raise ValueError("default_shot_seconds must be > 0")
        if width <= 0 or height <= 0: raise ValueError("width and height must be > 0")
        payload: dict[str, Any] = {
            "target_duration_sec": target_duration_sec,
            "default_shot_seconds": default_shot_seconds,
            "acceleration_profile": self._required_text(acceleration_profile, "acceleration_profile"),
            "width": width,
            "height": height,
        }
        if source_id is not None: payload["source_id"] = self._required_text(source_id, "source_id")
        if language is not None: payload["language"] = self._required_text(language, "language")
        if visual_style is not None: payload["visual_style"] = list(visual_style)
        if world_rules is not None: payload["world_rules"] = list(world_rules)
        result = self._object("POST", f"/api/v1/jobs/{job_id}/flows/source-to-film", payload)
        required = ("os_project_id", "os_job_id", "studio_project_id", "studio_source_id", "queue_id")
        missing = [key for key in required if not isinstance(result.get(key), str) or not result[key].strip()]
        if missing:
            raise EngineeringOSContractError(
                "source-to-film response missing required provenance fields: " + ", ".join(missing)
            )
        if result["os_job_id"] != job_id:
            raise EngineeringOSContractError("source-to-film response os_job_id does not match requested job")
        if not isinstance(result.get("artifact"), dict):
            raise EngineeringOSContractError("source-to-film response must contain OS provenance artifact")
        return result

    def list_job_artifacts(self, job_id: str) -> list[dict[str, Any]]:
        return self._items(f"/api/v1/jobs/{self._required_id(job_id, 'job_id')}/artifacts", "artifact")

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        return self._object("GET", f"/api/v1/artifacts/{self._required_id(artifact_id, 'artifact_id')}")

    def register_artifact(self, *, project_id: str, job_id: str | None, component_id: str | None,
                          kind: str, uri: str, media_type: str, checksum: str,
                          source_run_id: str | None = None) -> dict[str, Any]:
        project_id = self._required_id(project_id, "project_id")
        payload: dict[str, Any] = {
            "kind": self._required_text(kind, "kind"),
            "uri": self._required_text(uri, "uri"),
            "media_type": self._required_text(media_type, "media_type"),
            "checksum": self._required_text(checksum, "checksum"),
        }
        if job_id is not None: payload["job_id"] = self._required_id(job_id, "job_id")
        if component_id is not None: payload["component_id"] = self._required_text(component_id, "component_id")
        if source_run_id is not None: payload["source_run_id"] = self._required_text(source_run_id, "source_run_id")
        return self._object("POST", f"/api/v1/projects/{project_id}/artifacts", payload)

    # Review / approval governance. Approval is derived by AI-Engineering-OS from the
    # latest review of every current Artifact revision; OpenWorker does not invent a
    # second Approval entity.
    def list_job_reviews(self, job_id: str) -> list[dict[str, Any]]:
        return self._items(f"/api/v1/jobs/{self._required_id(job_id, 'job_id')}/reviews", "review")

    def list_artifact_reviews(self, artifact_id: str) -> list[dict[str, Any]]:
        return self._items(f"/api/v1/artifacts/{self._required_id(artifact_id, 'artifact_id')}/reviews", "review")

    def approval_status(self, job_id: str) -> dict[str, Any]:
        result = self._object("GET", f"/api/v1/jobs/{self._required_id(job_id, 'job_id')}/approval-status")
        if not isinstance(result.get("approved"), bool):
            raise EngineeringOSContractError("approval-status response must contain approved boolean")
        return result

    def submit_artifact_review(self, *, job_id: str, artifact_id: str, reviewer: str,
                               decision: str, comment: str = "") -> dict[str, Any]:
        job_id = self._required_id(job_id, "job_id")
        artifact_id = self._required_id(artifact_id, "artifact_id")
        reviewer = self._required_text(reviewer, "reviewer")
        decision = self._required_text(decision, "decision")
        if decision not in {"approved", "rejected", "rework"}:
            raise ValueError("decision must be approved, rejected, or rework")
        if decision in {"rejected", "rework"} and not comment.strip():
            raise ValueError("comment is required for rejected or rework review")
        return self._object("POST", f"/api/v1/artifacts/{artifact_id}/reviews", {
            "job_id": job_id,
            "reviewer": reviewer,
            "decision": decision,
            "comment": comment.strip(),
        })

    # Delivery/publish remains authoritative in AI-Engineering-OS. The server itself
    # verifies approval, current Artifact checksums and job state before publishing.
    def list_deliveries(self, job_id: str) -> list[dict[str, Any]]:
        return self._items(f"/api/v1/jobs/{self._required_id(job_id, 'job_id')}/deliveries", "delivery")

    def latest_delivery(self, job_id: str) -> dict[str, Any]:
        return self._object("GET", f"/api/v1/jobs/{self._required_id(job_id, 'job_id')}/deliveries/latest")

    def publish_job(self, *, job_id: str, publisher: str, note: str = "") -> dict[str, Any]:
        job_id = self._required_id(job_id, "job_id")
        publisher = self._required_text(publisher, "publisher")
        result = self._object("POST", f"/api/v1/jobs/{job_id}/publish",
                              {"publisher": publisher, "note": note.strip()})
        delivery = result.get("delivery")
        website = result.get("website")
        if not isinstance(delivery, dict) or not isinstance(website, dict):
            raise EngineeringOSContractError("publish response must contain delivery and website objects")
        return result

    def _items(self, path: str, item_name: str) -> list[dict[str, Any]]:
        items = self._request_json("GET", path).get("items")
        if not isinstance(items, list): raise EngineeringOSContractError(f"{path} response must contain an items list")
        if any(not isinstance(item, dict) for item in items):
            raise EngineeringOSContractError(f"{item_name} list contains a non-object item")
        return items

    def _object(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result = self._request_json(method, path, payload)
        if not isinstance(result, dict): raise EngineeringOSContractError(f"{path} response must be a JSON object")
        return result

    def _request_json(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None: headers["Content-Type"] = "application/json"
        response = self.transport.request(method, f"{self.config.base_url}{path}", body=body,
                                          headers=headers, timeout=self.config.timeout_seconds)
        decoded = self._decode_json(response.body, path)
        if not 200 <= response.status < 300:
            raise EngineeringOSHTTPError(response.status,
                code=decoded.get("error") if isinstance(decoded, dict) else None,
                message=decoded.get("message") if isinstance(decoded, dict) else None)
        if not isinstance(decoded, dict): raise EngineeringOSContractError(f"{path} response must be a JSON object")
        return decoded

    @staticmethod
    def _decode_json(body: bytes, path: str) -> Any:
        try: return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EngineeringOSContractError(f"{path} returned invalid JSON") from exc

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        value = value.strip()
        if not value: raise ValueError(f"{field} must not be empty")
        return value

    @classmethod
    def _required_id(cls, value: str, field: str) -> str:
        value = cls._required_text(value, field)
        if any(ch in value for ch in "/?#"): raise ValueError(f"{field} contains invalid path characters")
        return value