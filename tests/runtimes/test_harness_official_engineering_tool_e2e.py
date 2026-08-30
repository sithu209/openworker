from __future__ import annotations

import json
import os
import shutil
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from coworker.engine import ApprovalOutcome
from coworker.permissions import Mode, PermissionEngine
from coworker.runtimes.harness import AcpProcessClient, HarnessProcessConfig
from coworker.runtimes.harness_context_ingress import HarnessContextIngressServer
from coworker.runtimes.harness_engineering_tools import (
    EngineeringOSToolClient,
    HarnessEngineeringToolGateway,
)
from coworker.runtimes.harness_permissions import (
    HarnessPermissionBridge,
    HarnessToolContextRegistry,
)


PLUGIN = Path(__file__).resolve().parents[2] / "harness" / "upstream-plugin" / "openworker-engineering-tools.ts"


class _FakeEngineeringOS:
    def __init__(self) -> None:
        owner = self
        self.discovery_count = 0
        self.invocations: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _json(self, status: int, payload: dict) -> None:
                raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/api/v1/ai/tools/mcp":
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                owner.discovery_count += 1
                self._json(
                    HTTPStatus.OK,
                    {
                        "tools": [
                            {
                                "name": "budget__calculate",
                                "description": "Calculate and persist an engineering budget.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"amount": {"type": "number"}},
                                    "required": ["amount"],
                                    "additionalProperties": False,
                                },
                                "annotations": {
                                    "canonical_tool_id": "budget.calculate",
                                    "side_effect": "mutate",
                                    "requires_job_scope": True,
                                    "cost_class": "high",
                                },
                            }
                        ]
                    },
                )

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/api/v1/ai/tools/budget.calculate/invoke":
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.invocations.append(body)
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "tool": "budget.calculate",
                        "run_id": "run-budget-1",
                        "summary": "budget calculated",
                        "result": {"total": body["arguments"]["amount"]},
                        "artifacts": [{"id": "budget-artifact-1"}],
                        "trace": ["h6.2"],
                        "warnings": [],
                        "assumptions": [],
                        "evidence": [],
                        "next_possible_tools": [],
                        "retryable": False,
                        "recovery_actions": [],
                        "error": None,
                    },
                )

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "_FakeEngineeringOS":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2.0)


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for official Harness E2E")
    return node


def _root() -> Path:
    raw = os.environ.get("DSH_HARNESS_ROOT", "").strip()
    if not raw:
        pytest.skip("DSH_HARNESS_ROOT is not set")
    root = Path(raw).resolve()
    if not root.exists():
        pytest.fail(f"DSH_HARNESS_ROOT does not exist: {root}")
    return root


def _yaml(value: str) -> str:
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


def _write_replay(path: Path) -> None:
    rows = [
        {
            "type": "session",
            "version": 0,
            "id": "openworker-h6-2-recorded",
            "createdAt": 1,
            "cwd": "{{cwd}}",
            "delegationDepth": 0,
        },
        {
            "type": "assistant/chunk",
            "seq": 1,
            "time": 1,
            "data": {
                "turn": 1,
                "step": 1,
                "chunk": {"type": "block-start", "index": 0, "blockType": "tool-call"},
            },
        },
        {
            "type": "assistant/chunk",
            "seq": 2,
            "time": 2,
            "data": {
                "turn": 1,
                "step": 1,
                "chunk": {
                    "type": "block-end",
                    "index": 0,
                    "block": {
                        "type": "tool-call",
                        "id": "call-budget-1",
                        "name": "budget__calculate",
                        "arguments": "{\"amount\":42}",
                    },
                },
            },
        },
        {
            "type": "assistant/chunk",
            "seq": 3,
            "time": 3,
            "data": {
                "turn": 1,
                "step": 1,
                "chunk": {"type": "finish", "reason": {"kind": "tool-calls"}},
            },
        },
        {
            "type": "assistant/chunk",
            "seq": 4,
            "time": 4,
            "data": {
                "turn": 1,
                "step": 2,
                "chunk": {"type": "block-start", "index": 0, "blockType": "text"},
            },
        },
        {
            "type": "assistant/chunk",
            "seq": 5,
            "time": 5,
            "data": {
                "turn": 1,
                "step": 2,
                "chunk": {
                    "type": "block-end",
                    "index": 0,
                    "block": {"type": "text", "text": "DONE"},
                },
            },
        },
        {
            "type": "assistant/chunk",
            "seq": 6,
            "time": 6,
            "data": {
                "turn": 1,
                "step": 2,
                "chunk": {"type": "finish", "reason": {"kind": "stop"}},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")


def _write_config(path: Path, root: Path, replay: Path) -> None:
    official = root / "examples" / "acp-agent" / "cordis.yml"
    path.write_text(
        f"""# H6.2 deterministic official Harness composition.
- id: base
  name: '@deepseek-ai/cordis-plugin-include'
  config:
    path: {_yaml(official.resolve().as_uri())}
    patches:
      - id: llm-deepseek
        name: '@deepseek-ai/dsh-llm-deepseek'
        disabled: true
      - insert:
          - id: llm-replay
            name: '@deepseek-ai/dsh-llm-replay'
            config:
              file: {_yaml(str(replay))}
              providers:
                - id: deepseek-official
                  name: DeepSeek Replay
                  models:
                    - id: deepseek-v4-pro
          - id: openworker-engineering-tools
            name: {_yaml(PLUGIN.resolve().as_uri())}
""",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_official_harness_agent_loop_executes_approved_engineering_tool(tmp_path: Path) -> None:
    root = _root()
    root_tsconfig = root / "tsconfig.json"
    bin_ts = root / "packages" / "examples" / "acp-demo" / "src" / "bin.ts"
    if not PLUGIN.exists() or not root_tsconfig.exists() or not bin_ts.exists():
        pytest.fail("pinned Harness/OpenWorker H6.2 source inputs are incomplete")

    replay = tmp_path / "replay.jsonl"
    config = tmp_path / "cordis.h6-2.yml"
    _write_replay(replay)
    _write_config(config, root, replay)

    with _FakeEngineeringOS() as fake_os:
        policy_http = httpx.Client()
        os_client = EngineeringOSToolClient(fake_os.base_url, client=policy_http)
        contexts = HarnessToolContextRegistry()
        gateway = HarnessEngineeringToolGateway(os_client, contexts)
        gateway.refresh()
        approvals = []

        async def approver(request):
            approvals.append(request)
            return ApprovalOutcome.ONCE

        bridge = HarnessPermissionBridge(
            permissions=PermissionEngine(tmp_path, mode=Mode.INTERACTIVE),
            approver=approver,
            resolve_context=contexts.resolve,
        )

        with HarnessContextIngressServer(gateway, token="h6-2-secret") as ingress:
            env = {
                "DSH_PERMISSION_MODE": "workspace-write",
                "DSH_HOME": str(tmp_path / ".dsh"),
                "DSH_AGENTS_HOME": str(tmp_path / ".agents"),
                "DSH_SNAPSHOT_SESSIONS_ROOT": str(tmp_path / ".sessions"),
                "TSX_TSCONFIG_PATH": str(root_tsconfig),
                "OPENWORKER_ENGINEERING_OS_BASE_URL": fake_os.base_url,
                "OPENWORKER_HARNESS_CONTEXT_URL": ingress.address.base_url,
                "OPENWORKER_HARNESS_CONTEXT_TOKEN": ingress.address.token,
                "OPENWORKER_ENGINEERING_PROJECT_ID": "project-h6-2",
                "OPENWORKER_ENGINEERING_JOB_ID": "job-h6-2",
                "OPENWORKER_ENGINEERING_COMPONENT_ID": "budget-main",
            }
            updates: list[dict] = []
            client = AcpProcessClient(
                HarnessProcessConfig(
                    command=(
                        _node(),
                        "--import",
                        "tsx",
                        str(bin_ts),
                        "--config",
                        str(config),
                    ),
                    cwd=root,
                    env=env,
                    startup_timeout_s=30.0,
                    request_timeout_s=30.0,
                ),
                on_update=updates.append,
                on_permission=bridge,
            )
            try:
                hello = await client.start()
                assert hello["protocolVersion"] == 1
                session_id = await client.new_session(tmp_path)
                stop_reason = await client.prompt(session_id, "Run the deterministic budget task.")
                assert stop_reason == "end_turn"
            finally:
                await client.close()
                policy_http.close()

        committed = [
            params["update"]["content"]["text"]
            for params in updates
            if params.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
            and params.get("update", {}).get("content", {}).get("type") == "text"
        ]
        assert "".join(committed) == "DONE"
        assert len(approvals) == 1
        assert approvals[0].tool_name == "budget__calculate"
        assert approvals[0].arguments == {"amount": 42}
        assert approvals[0].metadata.canonical_tool_id == "budget.calculate"
        assert fake_os.invocations == [
            {
                "project_id": "project-h6-2",
                "job_id": "job-h6-2",
                "arguments": {"amount": 42},
                "component_id": "budget-main",
            }
        ]
        # tools/result cleanup is intentionally async best-effort; give the localhost
        # delete a short deterministic window before asserting the registry is clear.
        for _ in range(100):
            if contexts.resolve("call-budget-1") is None:
                break
            time.sleep(0.01)
        assert contexts.resolve("call-budget-1") is None
        assert fake_os.discovery_count >= 2  # OpenWorker policy catalog + Harness plugin catalog
