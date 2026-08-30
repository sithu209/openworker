"""One-time local OAuth bootstrap for OpenWorker Google Drive transport.

This command is intentionally interactive and must run on the local Windows user
that owns the OpenWorker runtime. It never prints refresh/access tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DEFAULT_FILENAME = "google-drive-authorized-user.json"


class DriveAuthLoginError(RuntimeError):
    pass


def default_credentials_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME")
    if base:
        return (Path(base).expanduser() / "OpenWorker" / DEFAULT_FILENAME).resolve()
    return (Path.home() / ".config" / "openworker" / DEFAULT_FILENAME).resolve()


def _set_user_env(name: str, value: str) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["setx", name, value],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise DriveAuthLoginError(f"failed to persist user environment variable {name}: {detail}")
        os.environ[name] = value
        return
    os.environ[name] = value


def login(client_secrets: str | Path, *, output: str | Path | None = None, no_browser: bool = False) -> dict[str, str]:
    source = Path(client_secrets).expanduser().resolve()
    if not source.is_file():
        raise DriveAuthLoginError(f"OAuth client-secrets file unavailable: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DriveAuthLoginError(f"invalid OAuth client-secrets JSON: {source}") from exc
    if not isinstance(payload, dict) or not (payload.get("installed") or payload.get("web")):
        raise DriveAuthLoginError("OAuth client-secrets JSON must contain an installed or web application definition")

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise DriveAuthLoginError("google-auth-oauthlib is required; reinstall/update OpenWorker") from exc

    target = Path(output).expanduser().resolve() if output else default_credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(source), scopes=[DRIVE_SCOPE])
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        authorization_prompt_message="Open this URL in a browser on the O87 user session:\n{url}",
        success_message="OpenWorker Google Drive authorization completed. You may close this browser window.",
        open_browser=not no_browser,
        access_type="offline",
        prompt="consent",
    )
    refresh_token = str(credentials.refresh_token or "").strip()
    if not refresh_token:
        raise DriveAuthLoginError("Google authorization returned no refresh token; revoke prior consent and run auth-login again")

    # authorized_user JSON is the canonical durable credential format already consumed
    # by DriveCredentials.resolve(). Never emit its secret fields to stdout.
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(credentials.to_json(), encoding="utf-8")
    os.replace(temp, target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    _set_user_env("OPENWORKER_GOOGLE_CREDENTIALS_FILE", str(target))
    return {
        "status": "AUTHORIZED",
        "credential_file": str(target),
        "scope": DRIVE_SCOPE,
        "environment_variable": "OPENWORKER_GOOGLE_CREDENTIALS_FILE",
        "next_step": "restart OpenWorker service/user process, then run openworker-drive auth-check",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openworker-drive-auth-login")
    parser.add_argument("--client-secrets", required=True, help="Google OAuth desktop client JSON downloaded locally; never commit this file")
    parser.add_argument("--output", help="authorized_user credential output path; defaults under LOCALAPPDATA/OpenWorker")
    parser.add_argument("--no-browser", action="store_true", help="print authorization URL instead of opening the default browser")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = login(args.client_secrets, output=args.output, no_browser=args.no_browser)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except DriveAuthLoginError as exc:
        print(f"OPENWORKER_DRIVE_AUTH_LOGIN_FAIL {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
