"""H7 Project Workspace bootstrap client for go-tool-runtime.

OpenWorker does not discover engineering context itself. For an engineering
workspace it asks go-tool-runtime to start the agent session and returns the
bounded prompt/AgentInformationPack produced by that authority. During a long
job the model may query go-tool-runtime again whenever tool choice, parameters,
or success criteria are uncertain. AI-Engineering-OS remains the separate
execution authority exposed by H6.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx


class ToolRuntimeBootstrapError(RuntimeError):
    """Raised when the information authority cannot produce trusted context."""


@dataclass(frozen=True)
class ToolRuntimeBootstrap:
    session_id: str
    project: str
    goal: str
    prompt: str
    information_pack: dict[str, Any]


@dataclass(frozen=True)
class ToolRuntimeQuery:
    session_id: str
    project: str
    question: str
    prompt: str
    information_pack: dict[str, Any]
    readiness: dict[str, Any]


class ToolRuntimeBootstrapClient:
    """Fail-closed client over go-tool-runtime's agent information endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8848",
        *,
        timeout_s: float = 30.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            raise ValueError("go-tool-runtime base_url is required")
        self.base_url = base
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_s, headers={"Accept": "application/json"})

    @classmethod
    def from_env(cls, *, client: Optional[httpx.Client] = None) -> "ToolRuntimeBootstrapClient":
        return cls(
            os.environ.get("OPENWORKER_TOOL_RUNTIME_URL", "http://127.0.0.1:8848"),
            client=client,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "ToolRuntimeBootstrapClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @staticmethod
    def _validated_workspace(workspace: str | os.PathLike[str]) -> Path:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            raise ToolRuntimeBootstrapError(f"Project Workspace does not exist: {root}")
        return root

    @staticmethod
    def _validate_information_pack(payload: dict[str, Any], root: Path) -> dict[str, Any]:
        information_pack = payload.get("information_pack")
        if not isinstance(information_pack, dict):
            raise ToolRuntimeBootstrapError("go-tool-runtime response has no AgentInformationPack")
        if information_pack.get("source") != "agent_information_pack":
            raise ToolRuntimeBootstrapError("untrusted information_pack source")
        workspace_info = information_pack.get("workspace")
        if not isinstance(workspace_info, dict):
            raise ToolRuntimeBootstrapError("AgentInformationPack has no workspace identity")
        reported_root = workspace_info.get("workspace_root")
        if not isinstance(reported_root, str) or not reported_root.strip():
            raise ToolRuntimeBootstrapError("AgentInformationPack has no workspace_root")
        try:
            reported = Path(reported_root).expanduser().resolve()
        except OSError as exc:
            raise ToolRuntimeBootstrapError(f"invalid workspace_root from information authority: {exc}") from exc
        if os.path.normcase(str(reported)) != os.path.normcase(str(root)):
            raise ToolRuntimeBootstrapError(
                f"AgentInformationPack workspace mismatch: expected {root}, got {reported}"
            )
        return information_pack

    def start(
        self,
        workspace: str | os.PathLike[str],
        goal: str,
        *,
        task: str = "",
        project: str = "",
        agent: str = "openworker-harness",
    ) -> ToolRuntimeBootstrap:
        root = self._validated_workspace(workspace)
        normalized_goal = str(goal or "").strip()
        if not normalized_goal:
            raise ToolRuntimeBootstrapError("goal must not be empty")
        project_key = str(project or "").strip() or root.name or "workspace"
        body = {
            "agent": str(agent or "openworker-harness").strip() or "openworker-harness",
            "project": project_key,
            "goal": normalized_goal,
            "task": str(task or ""),
            "workspace_root": str(root),
        }
        try:
            response = self.client.post(f"{self.base_url}/agent/start", json=body)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolRuntimeBootstrapError(f"go-tool-runtime bootstrap transport failed: {exc}") from exc
        if response.is_error:
            raise ToolRuntimeBootstrapError(
                f"go-tool-runtime /agent/start failed ({response.status_code}): {payload}"
            )
        if not isinstance(payload, dict):
            raise ToolRuntimeBootstrapError("go-tool-runtime /agent/start returned a non-object payload")

        session_id = payload.get("session_id")
        prompt = payload.get("prompt")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ToolRuntimeBootstrapError("go-tool-runtime bootstrap has no session_id")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ToolRuntimeBootstrapError("go-tool-runtime bootstrap has no prompt")
        information_pack = self._validate_information_pack(payload, root)
        required_markers = (
            "<AgentInformationPack>",
            "information_authority=go-tool-runtime",
            "execution_authority=AI-Engineering-OS",
        )
        if any(marker not in prompt for marker in required_markers):
            raise ToolRuntimeBootstrapError("bootstrap prompt is missing authority markers")

        return ToolRuntimeBootstrap(
            session_id=session_id.strip(),
            project=str(payload.get("project") or project_key),
            goal=str(payload.get("goal") or normalized_goal),
            prompt=prompt,
            information_pack=information_pack,
        )

    def query(
        self,
        workspace: str | os.PathLike[str],
        question: str,
        *,
        project: str,
        session_id: str = "",
        task: str = "",
    ) -> ToolRuntimeQuery:
        """Re-query go-tool-runtime during an existing job instead of guessing.

        This call is information-only: it must not dispatch or mutate execution.
        The model should use it whenever tool selection, parameters, diagnostics,
        or success criteria are uncertain.
        """
        root = self._validated_workspace(workspace)
        normalized_question = str(question or "").strip()
        project_key = str(project or "").strip()
        if not normalized_question:
            raise ToolRuntimeBootstrapError("question must not be empty")
        if not project_key:
            raise ToolRuntimeBootstrapError("project is required for repeat query")
        body = {
            "session_id": str(session_id or "").strip(),
            "project": project_key,
            "workspace_root": str(root),
            "question": normalized_question,
            "task": str(task or ""),
        }
        try:
            response = self.client.post(f"{self.base_url}/agent/query", json=body)
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolRuntimeBootstrapError(f"go-tool-runtime query transport failed: {exc}") from exc
        if response.is_error:
            raise ToolRuntimeBootstrapError(
                f"go-tool-runtime /agent/query failed ({response.status_code}): {payload}"
            )
        if not isinstance(payload, dict):
            raise ToolRuntimeBootstrapError("go-tool-runtime /agent/query returned a non-object payload")
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ToolRuntimeBootstrapError("go-tool-runtime query has no prompt")
        information_pack = self._validate_information_pack(payload, root)
        readiness = payload.get("readiness")
        if not isinstance(readiness, dict):
            raise ToolRuntimeBootstrapError("go-tool-runtime query has no readiness snapshot")
        if "information_authority=go-tool-runtime" not in prompt:
            raise ToolRuntimeBootstrapError("query prompt is missing information authority marker")
        return ToolRuntimeQuery(
            session_id=str(payload.get("session_id") or session_id or "").strip(),
            project=str(payload.get("project") or project_key),
            question=str(payload.get("question") or normalized_question),
            prompt=prompt,
            information_pack=information_pack,
            readiness=readiness,
        )

    def finish(self, session_id: str, *, summary: str, result: str = "success") -> None:
        session = str(session_id or "").strip()
        if not session:
            return
        body = {"session_id": session, "summary": str(summary or ""), "result": str(result or "success")}
        try:
            response = self.client.post(f"{self.base_url}/agent/finish", json=body)
            if response.is_error:
                raise ToolRuntimeBootstrapError(
                    f"go-tool-runtime /agent/finish failed ({response.status_code}): {response.text}"
                )
        except httpx.HTTPError as exc:
            raise ToolRuntimeBootstrapError(f"go-tool-runtime finish transport failed: {exc}") from exc


__all__ = [
    "ToolRuntimeBootstrap",
    "ToolRuntimeQuery",
    "ToolRuntimeBootstrapClient",
    "ToolRuntimeBootstrapError",
]
