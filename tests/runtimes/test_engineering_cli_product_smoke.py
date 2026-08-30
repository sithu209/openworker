from __future__ import annotations

import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from coworker import engineering_cli
from coworker.runtimes.harness import HarnessProcessConfig


FIXTURE = Path(__file__).parent / "fixtures" / "mock_acp_server.py"


class _Server:
    def __init__(self, handler_type: type[BaseHTTPRequestHandler]) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "_Server":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2.0)


def _engineering_os(seen: list[tuple[str, str, dict | None]]) -> _Server:
    projects: list[dict] = []

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

        def _body(self) -> dict | None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else None

        def do_GET(self) -> None:  # noqa: N802
            seen.append(("GET", self.path, None))
            if self.path == "/api/v1/projects":
                self._json(HTTPStatus.OK, {"items": projects})
                return
            if self.path == "/api/v1/ai/tools/mcp":
                self._json(
                    HTTPStatus.OK,
                    {
                        "tools": [
                            {
                                "name": "workspace__inspect",
                                "description": "Inspect the current engineering workspace.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "additionalProperties": False,
                                },
                                "annotations": {
                                    "canonical_tool_id": "workspace.inspect",
                                    "side_effect": "read",
                                    "requires_job_scope": False,
                                    "cost_class": "low",
                                },
                            }
                        ]
                    },
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            body = self._body()
            seen.append(("POST", self.path, body))
            if self.path == "/api/v1/projects":
                assert isinstance(body, dict)
                created = {"id": "prj-product-smoke", "status": "draft", **body}
                projects.append(created)
                self._json(HTTPStatus.CREATED, created)
                return
            if self.path == "/api/v1/jobs":
                assert isinstance(body, dict)
                self._json(
                    HTTPStatus.CREATED,
                    {"id": "job-product-smoke", "status": "draft", **body},
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    return _Server(Handler)


def _tool_runtime(workspace: Path, seen: list[tuple[str, dict]]) -> _Server:
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

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            seen.append((self.path, body))
            if self.path == "/agent/start":
                self._json(
                    HTTPStatus.OK,
                    {
                        "session_id": "session-product-smoke",
                        "project": body["project"],
                        "goal": body["goal"],
                        "information_pack": {
                            "source": "agent_information_pack",
                            "workspace": {
                                "workspace_id": "workspace-product-smoke",
                                "workspace_root": str(workspace.resolve()),
                            },
                        },
                        "prompt": (
                            "<AgentInformationPack>\n"
                            f"workspace_root={workspace.resolve()}\n"
                            "information_authority=go-tool-runtime\n"
                            "execution_authority=AI-Engineering-OS\n"
                            "</AgentInformationPack>"
                        ),
                    },
                )
                return
            if self.path == "/agent/finish":
                self._json(
                    HTTPStatus.OK,
                    {"session_id": body["session_id"], "status": body["result"]},
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    return _Server(Handler)


def test_openworker_engineering_cli_closes_projectroot_product_lifecycle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "AGENTS.md").write_text("Use go-tool-runtime for information.\n", encoding="utf-8")
    (tmp_path / "TASK.md").write_text("Build the Project Workspace deliverable.\n", encoding="utf-8")
    os_seen: list[tuple[str, str, dict | None]] = []
    runtime_seen: list[tuple[str, dict]] = []

    def deterministic_process(workspace: Path) -> HarnessProcessConfig:
        return HarnessProcessConfig(
            command=(sys.executable, str(FIXTURE)),
            cwd=workspace,
            startup_timeout_s=5.0,
            request_timeout_s=5.0,
        )

    monkeypatch.setattr(engineering_cli, "packaged_process_config", deterministic_process)

    with _engineering_os(os_seen) as fake_os, _tool_runtime(tmp_path, runtime_seen) as fake_runtime:
        rc = engineering_cli.main(
            [
                "--workspace",
                str(tmp_path),
                "--engineering-os-url",
                fake_os.base_url,
                "--tool-runtime-url",
                fake_runtime.base_url,
            ]
        )

    assert rc == 0
    output = capsys.readouterr().out
    assert "information_authority=go-tool-runtime" in output
    assert "execution_authority=AI-Engineering-OS" in output
    assert "Build the Project Workspace deliverable." in output

    project_create = next(body for method, path, body in os_seen if method == "POST" and path == "/api/v1/projects")
    job_create = next(body for method, path, body in os_seen if method == "POST" and path == "/api/v1/jobs")
    assert project_create is not None
    assert project_create["metadata"]["workspace_root"] == str(tmp_path.resolve())
    assert job_create is not None
    assert job_create["project_id"] == "prj-product-smoke"
    assert job_create["user_request"] == "Build the Project Workspace deliverable."
    assert job_create["metadata"]["workspace_root"] == str(tmp_path.resolve())
    assert any(method == "GET" and path == "/api/v1/ai/tools/mcp" for method, path, _ in os_seen)

    start = next(body for path, body in runtime_seen if path == "/agent/start")
    finish = next(body for path, body in runtime_seen if path == "/agent/finish")
    assert start["workspace_root"] == str(tmp_path.resolve())
    # go-tool preflight happens before the OS Project exists. Its project key is
    # therefore the stable workspace identity, not the later OS project id.
    assert start["project"] == tmp_path.name
    assert start["project"] != "prj-product-smoke"
    assert start["goal"] == "Build the Project Workspace deliverable."
    assert finish["session_id"] == "session-product-smoke"
    assert finish["result"] == "success"
