from __future__ import annotations

import os
import shutil
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from coworker.runtimes.harness import AcpProcessClient, HarnessProcessConfig


PLUGIN = Path(__file__).resolve().parents[2] / "harness" / "upstream-plugin" / "openworker-engineering-tools.ts"


class _FakeEngineeringOS:
    def __init__(self) -> None:
        owner = self
        self.discovery_count = 0

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/api/v1/ai/tools/mcp":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                owner.discovery_count += 1
                payload = (
                    '{"tools":['
                    '{"name":"workspace__inspect","description":"workspace status",'
                    '"inputSchema":{"type":"object","properties":{},"additionalProperties":false},'
                    '"annotations":{"canonical_tool_id":"workspace.inspect","side_effect":"read",'
                    '"requires_job_scope":false,"cost_class":"low"}},'
                    '{"name":"budget__calculate","description":"budget mutation",'
                    '"inputSchema":{"type":"object","properties":{"amount":{"type":"number"}},'
                    '"required":["amount"],"additionalProperties":false},'
                    '"annotations":{"canonical_tool_id":"budget.calculate","side_effect":"mutate",'
                    '"requires_job_scope":true,"cost_class":"high"}}]}'
                ).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

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
        pytest.skip("node is required for official Harness smoke")
    return node


def _harness_root() -> Path:
    raw = os.environ.get("DSH_HARNESS_ROOT", "").strip()
    if not raw:
        pytest.skip("DSH_HARNESS_ROOT is not set")
    root = Path(raw).resolve()
    if not root.exists():
        pytest.fail(f"DSH_HARNESS_ROOT does not exist: {root}")
    return root


def _yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


def _plugin_module_specifier(path: Path) -> str:
    # Cordis ultimately forwards this value to Node's ESM loader. POSIX absolute
    # paths work as path-like specifiers, but on Windows `C:/...` is parsed as
    # an unsupported `c:` URL scheme. A file URI is portable on both platforms.
    return path.resolve().as_uri()


@pytest.mark.asyncio
async def test_official_harness_loads_openworker_dynamic_tool_plugin(tmp_path: Path) -> None:
    root = _harness_root()
    if not PLUGIN.exists():
        pytest.fail(f"OpenWorker Harness plugin missing: {PLUGIN}")

    official_config = root / "examples" / "acp-agent" / "cordis.yml"
    bin_ts = root / "packages" / "examples" / "acp-demo" / "src" / "bin.ts"
    root_tsconfig = root / "tsconfig.json"
    for required in (official_config, bin_ts, root_tsconfig):
        if not required.exists():
            pytest.fail(f"pinned Harness source path missing: {required}")

    # Keep the official composition byte-for-byte, adding only one ordinary Cordis
    # plugin row. The ACP wire and upstream packages are not patched or forked.
    config = tmp_path / "cordis.openworker.yml"
    base = official_config.read_text(encoding="utf-8")

    with _FakeEngineeringOS() as fake_os:
        plugin_row = f"""

# OpenWorker H6.1 local plugin inserted by interoperability smoke.
- id: openworker-engineering-tools
  name: {_yaml_string(_plugin_module_specifier(PLUGIN))}
"""
        config.write_text(base + plugin_row, encoding="utf-8")

        env = {
            "DEEPSEEK_API_KEY": "sk-dummy-for-boot",
            "DSH_PERMISSION_MODE": "workspace-write",
            "DSH_HOME": str(tmp_path / ".dsh"),
            "DSH_AGENTS_HOME": str(tmp_path / ".agents"),
            "DSH_SNAPSHOT_SESSIONS_ROOT": str(tmp_path / ".sessions"),
            "TSX_TSCONFIG_PATH": str(root_tsconfig),
            "OPENWORKER_ENGINEERING_OS_BASE_URL": fake_os.base_url,
            "OPENWORKER_HARNESS_CONTEXT_URL": "http://127.0.0.1:9",
            "OPENWORKER_HARNESS_CONTEXT_TOKEN": "smoke-only-token",
            "OPENWORKER_ENGINEERING_PROJECT_ID": "project-smoke",
            "OPENWORKER_ENGINEERING_JOB_ID": "job-smoke",
        }
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
                request_timeout_s=15.0,
            )
        )
        try:
            hello = await client.start()
            assert hello["protocolVersion"] == 1
            session_id = await client.new_session(tmp_path)
            assert session_id
            assert fake_os.discovery_count == 1
            assert client.running
        finally:
            await client.close()
