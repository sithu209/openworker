from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / ".github" / "workflows" / "dispatch-local-supervisor-command-oda.yml"
INSTALL = ROOT / ".github" / "workflows" / "install-openworkerctl-oda.yml"
TRANSPORT = ROOT / "scripts" / "invoke-local-supervisor-command-transport.ps1"
CTL = ROOT / "go-runtime" / "cmd" / "openworkerctl" / "main.go"


def test_dispatch_is_fixed_oda_transport_only_contract():
    workflow = DISPATCH.read_text(encoding="utf-8")
    transport = TRANSPORT.read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, Windows, X64, ODA]" in workflow
    assert "DESKTOP-ODAQN0D" in workflow
    assert "timeout-minutes: 2" in workflow
    assert "command-requests/oda.json" in workflow
    assert "command-results/oda.json" in workflow
    assert "openworker.command-request.v1" in workflow
    assert "openworker.command-result.v1" in workflow
    assert "invoke-local-supervisor-command-transport.ps1" in workflow
    assert "contents: write" in workflow

    for command in ("supervisor_status", "case_status", "case_continue", "queue_clear"):
        assert f"- {command}" in workflow
        assert command in transport

    assert "openworkerctl.exe" in transport
    assert "case','continue','0005" in transport
    assert "queue','clear','DESKTOP-ODAQN0D" in transport
    assert "github_action_used_for_command_transport=$true" in transport
    assert "github_action_used_for_business_execution=$false" in transport
    assert "Test-Accepted" in transport
    assert "case_continue did not return accepted=true" in transport
    assert "git push origin HEAD:main" in workflow

    combined = workflow + "\n" + transport
    forbidden = (
        "actions/upload-artifact",
        "SaveVideo",
        "blender",
        "comfyui",
        "presentation/storyboard-text-only.pptx",
        "drive.google.com",
        "googleapis.com/upload",
        "Start-Sleep -Seconds 60",
    )
    for token in forbidden:
        assert token.lower() not in combined.lower()


def test_result_writeback_cannot_retrigger_transport_workflow():
    text = DISPATCH.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]

    assert "'command-requests/oda.json'" in trigger_block
    assert "command-results/oda.json" not in trigger_block
    assert "github_action_used_for_business_execution=$false" in text


def test_dispatch_has_no_free_form_case_machine_url_or_shell_inputs():
    text = DISPATCH.read_text(encoding="utf-8")
    dispatch_input_block = text.split("permissions:", 1)[0]

    assert "inputs:\n      command:" in dispatch_input_block
    assert "case_id:" not in dispatch_input_block
    assert "machine:" not in dispatch_input_block
    assert "url:" not in dispatch_input_block
    assert "script:" not in dispatch_input_block
    assert "shell_command:" not in dispatch_input_block


def test_push_request_is_fail_closed_to_schema_machine_case_and_allowlist():
    text = DISPATCH.read_text(encoding="utf-8")

    assert "unsupported request schema" in text
    assert "unsupported request machine" in text
    assert "unsupported request case_id" in text
    assert "request_id is required" in text
    assert "unsupported command=" in text
    assert "DESKTOP-ODAQN0D" in text
    assert "0005" in text


def test_installer_verifies_real_local_supervisor_before_transport_use():
    text = INSTALL.read_text(encoding="utf-8")

    assert "runs-on: [self-hosted, Windows, X64, ODA]" in text
    assert "install-openworkerctl.ps1" in text
    assert "openworkerctl.exe" in text
    assert "supervisor status" in text
    assert "OPERATIONAL" in text
    assert "LOCAL_SUPERVISOR" in text
    assert "github_action_used_for_business_execution=$false" in text


def test_openworkerctl_remains_localhost_fail_closed():
    text = CTL.read_text(encoding="utf-8")

    assert 'const defaultServer="http://127.0.0.1:8848"' in text
    assert 'id!="0005"' in text
    assert '"0005","DESKTOP-ODAQN0D"' in text
    assert 'server must be http localhost:8848 without path' in text
    assert 'GitHub business execution forbidden' in text
