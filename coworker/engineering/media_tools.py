"""Thin managed-media facade over ComfyX's authoritative ai-tool-protocol surface.

OpenWorker does not reproduce MiniMax H3 workflow construction, ComfyUI discovery,
submission, polling, or artifact extraction.  Those remain owned by ComfyX.  This module
only adapts the existing ``comfyx.minimax_h3.generate`` tool into OpenWorker's existing
vetted Tool Registry surface and validates the protocol response fail-closed.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import aisuite as ai


PROTOCOL_VERSION = "ai-tool-protocol/1.0.0"
H3_TOOL_ID = "comfyx.minimax_h3.generate"
_H3_ARGUMENTS = frozenset({
    "modelMode",
    "prompt",
    "firstFrameUri",
    "lastFrameUri",
    "singleFrameRole",
    "referenceImages",
    "referenceVideos",
    "referenceVideoAudios",
    "referenceAudios",
    "referenceImageSize",
    "durationSeconds",
    "width",
    "height",
    "seed",
    "steps",
    "cfg",
    "timeout",
    "client_id",
    "compile_only",
})


class ComfyXToolError(RuntimeError):
    """Raised when the authoritative ComfyX tool contract cannot be satisfied."""


@dataclass(frozen=True)
class ComfyXH3Result:
    request_id: str
    prompt_id: str
    mode: str
    runtime: Mapping[str, Any]
    required_nodes: tuple[str, ...]
    history: Any
    artifacts: tuple[Any, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "openworker.comfyx-h3-result/v1",
            "authority": "ComfyX",
            "protocol_version": PROTOCOL_VERSION,
            "tool_id": H3_TOOL_ID,
            "request_id": self.request_id,
            "prompt_id": self.prompt_id,
            "mode": self.mode,
            "runtime": dict(self.runtime),
            "required_nodes": list(self.required_nodes),
            "history": self.history,
            "artifacts": list(self.artifacts),
            "warnings": list(self.warnings),
            "publish_performed": False,
            "external_send_performed": False,
        }


class ComfyXToolClient:
    """Execute ComfyX's existing JSON-file tool protocol without owning media logic."""

    def __init__(
        self,
        *,
        executable: str = "comfyx-tool",
        timeout_seconds: float = 3700.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def generate_minimax_h3(
        self,
        arguments: Mapping[str, Any],
        *,
        request_id: str | None = None,
    ) -> ComfyXH3Result:
        if not isinstance(arguments, Mapping):
            raise ComfyXToolError("MiniMax H3 arguments must be an object")
        args = dict(arguments)
        unknown = sorted(set(args) - _H3_ARGUMENTS)
        if unknown:
            raise ComfyXToolError(f"unsupported MiniMax H3 arguments: {', '.join(unknown)}")
        prompt = args.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ComfyXToolError("MiniMax H3 prompt is required")
        if args.get("compile_only") is True:
            raise ComfyXToolError("media generation facade does not accept compile_only=true")

        rid = (request_id or f"openworker-e7-{uuid.uuid4().hex}").strip()
        if not rid:
            raise ComfyXToolError("request_id must not be empty")
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": rid,
            "tool_id": H3_TOOL_ID,
            "arguments": args,
        }

        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="openworker-comfyx-", encoding="utf-8",
                delete=False,
            ) as handle:
                json.dump(request, handle, ensure_ascii=False)
                handle.write("\n")
                path = Path(handle.name)
            completed = self._runner(
                [self.executable, "execute", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ComfyXToolError(f"ComfyX tool execution failed: {exc}") from exc
        finally:
            if path is not None:
                try:
                    os.unlink(path)
                except OSError:
                    pass

        try:
            payload = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ComfyXToolError(
                f"ComfyX tool returned invalid JSON; stderr={completed.stderr.strip()[:500]}"
            ) from exc
        if not isinstance(payload, dict):
            raise ComfyXToolError("ComfyX tool response must be an object")
        if payload.get("protocol_version") != PROTOCOL_VERSION:
            raise ComfyXToolError("ComfyX tool protocol_version mismatch")
        if payload.get("request_id") != rid:
            raise ComfyXToolError("ComfyX tool request_id mismatch")
        if payload.get("tool_id") != H3_TOOL_ID:
            raise ComfyXToolError("ComfyX tool_id mismatch")
        if completed.returncode != 0 or payload.get("status") != "succeeded":
            error = payload.get("error")
            if isinstance(error, Mapping):
                message = str(error.get("message") or error.get("code") or "").strip()
            else:
                message = str(error or "").strip()
            raise ComfyXToolError(f"ComfyX H3 generation failed: {message or completed.stderr.strip()}")

        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ComfyXToolError("ComfyX H3 response missing data object")
        prompt_id = str(data.get("prompt_id") or "").strip()
        if not prompt_id:
            raise ComfyXToolError("ComfyX H3 response missing prompt_id")
        mode = str(data.get("mode") or "").strip()
        if not mode:
            raise ComfyXToolError("ComfyX H3 response missing mode")
        runtime = data.get("runtime")
        if not isinstance(runtime, Mapping):
            raise ComfyXToolError("ComfyX H3 response missing runtime object")
        required_nodes = data.get("required_nodes")
        if not isinstance(required_nodes, Sequence) or isinstance(required_nodes, (str, bytes)):
            raise ComfyXToolError("ComfyX H3 response required_nodes must be an array")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise ComfyXToolError("ComfyX H3 response artifacts must be an array")
        warnings = payload.get("warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            raise ComfyXToolError("ComfyX H3 response warnings must be a string array")
        return ComfyXH3Result(
            request_id=rid,
            prompt_id=prompt_id,
            mode=mode,
            runtime=dict(runtime),
            required_nodes=tuple(str(item) for item in required_nodes),
            history=data.get("history"),
            artifacts=tuple(artifacts),
            warnings=tuple(warnings),
        )


def managed_media_tools(client: ComfyXToolClient | None = None) -> list[Any]:
    """Expose ComfyX through the existing vetted OpenWorker Tool Registry only."""

    api = client or ComfyXToolClient()

    def engineering_generate_minimax_h3(
        prompt: str,
        modelMode: str = "FL2VA",
        durationSeconds: int = 6,
        width: int = 1344,
        height: int = 768,
        firstFrameUri: str | None = None,
        lastFrameUri: str | None = None,
        singleFrameRole: str | None = None,
        referenceImages: list[str] | None = None,
        referenceVideos: list[str] | None = None,
        referenceVideoAudios: list[str] | None = None,
        referenceAudios: list[str] | None = None,
        referenceImageSize: str | None = None,
        seed: int | None = None,
        steps: int = 25,
        cfg: float = 5.0,
        timeout: str = "60m",
        client_id: str | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "modelMode": modelMode,
            "durationSeconds": durationSeconds,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "timeout": timeout,
        }
        optional = {
            "firstFrameUri": firstFrameUri,
            "lastFrameUri": lastFrameUri,
            "singleFrameRole": singleFrameRole,
            "referenceImages": referenceImages,
            "referenceVideos": referenceVideos,
            "referenceVideoAudios": referenceVideoAudios,
            "referenceAudios": referenceAudios,
            "referenceImageSize": referenceImageSize,
            "seed": seed,
            "client_id": client_id,
        }
        arguments.update({key: value for key, value in optional.items() if value is not None})
        return api.generate_minimax_h3(arguments).to_dict()

    engineering_generate_minimax_h3.__coworker_schema__ = {
        "type": "function",
        "function": {
            "name": "engineering_generate_minimax_h3",
            "description": (
                "Generate MiniMax H3 audio-video through ComfyX's authoritative "
                "comfyx.minimax_h3.generate tool. Supports the five official reference modes."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "prompt": {"type": "string"},
                    "modelMode": {"type": "string", "enum": ["FL2VA", "Ref2VA"]},
                    "durationSeconds": {"type": "integer", "minimum": 4, "maximum": 15},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "firstFrameUri": {"type": ["string", "null"]},
                    "lastFrameUri": {"type": ["string", "null"]},
                    "singleFrameRole": {"type": ["string", "null"], "enum": ["first", "last", None]},
                    "referenceImages": {"type": ["array", "null"], "items": {"type": "string"}},
                    "referenceVideos": {"type": ["array", "null"], "items": {"type": "string"}},
                    "referenceVideoAudios": {"type": ["array", "null"], "items": {"type": "string"}},
                    "referenceAudios": {"type": ["array", "null"], "items": {"type": "string"}},
                    "referenceImageSize": {"type": ["string", "null"], "enum": ["match", "max", None]},
                    "seed": {"type": ["integer", "null"]},
                    "steps": {"type": "integer"},
                    "cfg": {"type": "number"},
                    "timeout": {"type": "string"},
                    "client_id": {"type": ["string", "null"]},
                },
                "required": ["prompt"],
            },
        },
    }
    engineering_generate_minimax_h3.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="engineering_generate_minimax_h3",
        category="engineering",
        risk_level="high",
        capabilities=["write", "engineering", "media", "video", "generation"],
        requires_approval=True,
        description="Execute authoritative MiniMax H3 generation in ComfyX; does not publish externally.",
    )
    return [engineering_generate_minimax_h3]


__all__ = [
    "ComfyXH3Result",
    "ComfyXToolClient",
    "ComfyXToolError",
    "H3_TOOL_ID",
    "PROTOCOL_VERSION",
    "managed_media_tools",
]
