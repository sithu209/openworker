from __future__ import annotations

import json
import subprocess

import pytest

from coworker.engineering.media_tools import (
    H3_TOOL_ID,
    PROTOCOL_VERSION,
    ComfyXToolClient,
    ComfyXToolError,
    managed_media_tools,
)


class FakeRunner:
    def __init__(self, response: dict, *, returncode: int = 0) -> None:
        self.response = response
        self.returncode = returncode
        self.calls: list[dict] = []

    def __call__(self, command, **kwargs):
        assert command[0:2] == ["comfyx-tool", "execute"]
        request = json.loads(open(command[2], encoding="utf-8").read())
        self.calls.append({"command": list(command), "request": request, "kwargs": dict(kwargs)})
        response = dict(self.response)
        response.setdefault("protocol_version", request["protocol_version"])
        response.setdefault("request_id", request["request_id"])
        response.setdefault("tool_id", request["tool_id"])
        return subprocess.CompletedProcess(
            command,
            self.returncode,
            stdout=json.dumps(response),
            stderr="",
        )


def _success_response() -> dict:
    return {
        "status": "succeeded",
        "data": {
            "mode": "text-to-audio-video",
            "runtime": {"kind": "desktop", "base_url": "http://127.0.0.1:8188"},
            "prompt_id": "prompt-123",
            "required_nodes": ["UNETLoader", "VAEDecode"],
            "history": {"prompt-123": {"status": {"completed": True}}},
        },
        "warnings": [],
        "artifacts": [{"filename": "h3.mp4", "type": "output"}],
    }


def test_client_uses_authoritative_ai_tool_protocol_and_preserves_outputs():
    runner = FakeRunner(_success_response())
    client = ComfyXToolClient(runner=runner)

    result = client.generate_minimax_h3(
        {"prompt": "cinematic bridge at dusk", "modelMode": "FL2VA", "width": 1344, "height": 768},
        request_id="req-1",
    )

    request = runner.calls[0]["request"]
    assert request == {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "req-1",
        "tool_id": H3_TOOL_ID,
        "arguments": {
            "prompt": "cinematic bridge at dusk",
            "modelMode": "FL2VA",
            "width": 1344,
            "height": 768,
        },
    }
    data = result.to_dict()
    assert data["prompt_id"] == "prompt-123"
    assert data["mode"] == "text-to-audio-video"
    assert data["artifacts"] == [{"filename": "h3.mp4", "type": "output"}]
    assert data["history"]["prompt-123"]["status"]["completed"] is True
    assert data["publish_performed"] is False
    assert data["external_send_performed"] is False


def test_client_rejects_unknown_arguments_before_execution():
    runner = FakeRunner(_success_response())
    client = ComfyXToolClient(runner=runner)
    with pytest.raises(ComfyXToolError, match="unsupported MiniMax H3 arguments"):
        client.generate_minimax_h3({"prompt": "video", "invented_private_endpoint": "x"})
    assert runner.calls == []


def test_client_rejects_compile_only_for_generation_facade():
    runner = FakeRunner(_success_response())
    client = ComfyXToolClient(runner=runner)
    with pytest.raises(ComfyXToolError, match="compile_only"):
        client.generate_minimax_h3({"prompt": "video", "compile_only": True})
    assert runner.calls == []


def test_client_fails_closed_when_prompt_id_is_missing():
    response = _success_response()
    del response["data"]["prompt_id"]
    runner = FakeRunner(response)
    with pytest.raises(ComfyXToolError, match="missing prompt_id"):
        ComfyXToolClient(runner=runner).generate_minimax_h3({"prompt": "video"}, request_id="req-2")


def test_client_fails_closed_on_protocol_identity_mismatch():
    response = _success_response()
    response["tool_id"] = "other.tool"
    runner = FakeRunner(response)
    with pytest.raises(ComfyXToolError, match="tool_id mismatch"):
        ComfyXToolClient(runner=runner).generate_minimax_h3({"prompt": "video"}, request_id="req-3")


def test_managed_tool_keeps_generation_approval_gated_and_does_not_publish():
    runner = FakeRunner(_success_response())
    tool = managed_media_tools(ComfyXToolClient(runner=runner))[0]
    metadata = tool.__aisuite_tool_metadata__
    assert tool.__name__ == "engineering_generate_minimax_h3"
    assert metadata.requires_approval is True

    result = tool(prompt="video", durationSeconds=6)
    assert result["prompt_id"] == "prompt-123"
    assert result["publish_performed"] is False
    assert result["external_send_performed"] is False
