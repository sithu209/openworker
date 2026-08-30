from __future__ import annotations

from pathlib import Path

from coworker.runtimes.engineering_host import EngineeringHarnessHost


def test_official_process_config_uses_file_uri_for_cordis_plugin(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    harness = tmp_path / "deepseek-harness"
    config_dir = harness / "examples" / "acp-agent"
    bin_dir = harness / "packages" / "examples" / "acp-demo" / "src"
    config_dir.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    (config_dir / "cordis.yml").write_text("plugins:\n", encoding="utf-8")
    (bin_dir / "bin.ts").write_text("// fixture\n", encoding="utf-8")
    (harness / "tsconfig.json").write_text("{}\n", encoding="utf-8")

    node = tmp_path / "node.exe"
    node.write_bytes(b"fixture")
    monkeypatch.setenv("DSH_HARNESS_ROOT", str(harness))
    monkeypatch.setenv("OPENWORKER_HARNESS_NODE", str(node))

    host = EngineeringHarnessHost(workspace=workspace)
    try:
        process = host._official_process_config()
        config_path = Path(process.command[-1])
        text = config_path.read_text(encoding="utf-8")
        plugin = (
            Path(__file__).resolve().parents[2]
            / "harness"
            / "upstream-plugin"
            / "openworker-engineering-tools.ts"
        ).resolve()
        assert f'name: "{plugin.as_uri()}"' in text
        assert f'name: "{str(plugin).replace(chr(92), "/")}"' not in text
    finally:
        # _official_process_config owns a temporary config directory even though
        # no Harness process was started.
        if host._temp_config is not None:
            host._temp_config.cleanup()
        host._scope_client.close()
        host._tool_client.close()
        host._bootstrap_client.close()
