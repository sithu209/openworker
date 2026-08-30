from pathlib import Path


def test_case0003_routes_on_generic_windows_and_fails_closed_on_ul7_host() -> None:
    workflow = Path('.github/workflows/case-0003-yujing-bridge-ul7.yml').read_text(encoding='utf-8')

    assert 'runs-on: [self-hosted, Windows, X64]' in workflow
    assert 'runs-on: [self-hosted, Windows, X64, UL7]' not in workflow
    assert 'CASE0003_ASSIGNED_HOST: DESKTOP-UL7V2VV' in workflow
    assert 'if($env:COMPUTERNAME -ine $env:CASE0003_ASSIGNED_HOST)' in workflow
    assert 'CASE0003_ASSIGNED_HOST_MISMATCH' in workflow
