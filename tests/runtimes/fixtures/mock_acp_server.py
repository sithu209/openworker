from __future__ import annotations

import json
import sys
import uuid

pending_prompt_id = None
pending_session = None


def send(frame):
    sys.stdout.write(json.dumps(frame, separators=(",", ":")) + "\n")
    sys.stdout.flush()


for raw in sys.stdin:
    if not raw.strip():
        continue
    frame = json.loads(raw)
    method = frame.get("method")
    params = frame.get("params") or {}
    request_id = frame.get("id")

    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": 1,
                "agentInfo": {"name": "mock-harness", "version": "h3"},
                "agentCapabilities": {"promptCapabilities": {"image": False, "audio": False, "embeddedContext": False}},
                "authMethods": [],
            },
        })
    elif method == "session/new":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"sessionId": str(uuid.uuid4())}})
    elif method == "session/prompt":
        text = "".join(block.get("text", "") for block in params.get("prompt", []) if block.get("type") == "text")
        if text == "HANG":
            pending_prompt_id = request_id
            pending_session = params.get("sessionId")
            continue
        send({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": params.get("sessionId"),
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": f"ACP:{text}"},
                },
            },
        })
        send({"jsonrpc": "2.0", "id": request_id, "result": {"stopReason": "end_turn"}})
    elif method == "session/cancel":
        if pending_prompt_id is not None and params.get("sessionId") == pending_session:
            send({"jsonrpc": "2.0", "id": pending_prompt_id, "result": {"stopReason": "cancelled"}})
            pending_prompt_id = None
            pending_session = None
    elif method == "mock/request-permission":
        send({
            "jsonrpc": "2.0",
            "id": 9001,
            "method": "session/request_permission",
            "params": {"sessionId": params.get("sessionId"), "toolCall": {"toolCallId": "call-1"}, "options": []},
        })
        send({"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}})
