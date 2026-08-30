from __future__ import annotations

import os
from pathlib import Path

import pytest

from coworker.runtimes.harness import AcpProcessClient, HarnessProcessConfig


@pytest.mark.asyncio
async def test_official_deepseek_harness_acp_initialize_and_new_session(tmp_path: Path) -> None:
    """Boot the pinned upstream ACP composition and prove OpenWorker wire compatibility.

    The Win11 verification workflow sets DSH_HARNESS_ROOT after checking out the
    exact upstream commit. A dummy DeepSeek key is sufficient because this smoke
    intentionally stops before session/prompt and therefore makes no model call.

    Upstream's own zero-build source launcher sets TSX_TSCONFIG_PATH so tsx can
    resolve @deepseek-ai/dsh-* workspace imports through the root tsconfig paths.
    This smoke mirrors that contract instead of depending on a prebuilt lib tree.
    """

    raw_root = os.environ.get("DSH_HARNESS_ROOT", "").strip()
    if not raw_root:
        pytest.skip("DSH_HARNESS_ROOT is required for the official ACP smoke")

    root = Path(raw_root).resolve()
    bin_script = root / "packages" / "examples" / "acp-demo" / "src" / "bin.ts"
    config_path = root / "examples" / "acp-agent" / "cordis.yml"
    tsconfig_path = root / "tsconfig.json"
    assert bin_script.is_file(), bin_script
    assert config_path.is_file(), config_path
    assert tsconfig_path.is_file(), tsconfig_path

    env = {
        "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "sk-dummy-for-boot"),
        "DSH_PERMISSION_MODE": "danger-full-access",
        "DSH_HOME": str(tmp_path / ".dsh"),
        "DSH_AGENTS_HOME": str(tmp_path / ".agents"),
        "TSX_TSCONFIG_PATH": str(tsconfig_path),
    }
    command = (
        "node",
        "--import",
        "tsx",
        str(bin_script),
        "--config",
        str(config_path),
    )
    client = AcpProcessClient(
        HarnessProcessConfig(
            command=command,
            cwd=root,
            env=env,
            startup_timeout_s=60.0,
            request_timeout_s=60.0,
        )
    )

    try:
        hello = await client.start()
        assert hello.get("agentInfo", {}).get("name") == "deepseek-harness-acp"
        session_id = await client.new_session(tmp_path)
        assert isinstance(session_id, str)
        assert session_id
        assert client.running
    finally:
        await client.close()
