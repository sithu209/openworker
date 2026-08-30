"""Resolve one readable user-scoped OpenWorker Google Drive SecretStore without exposing secrets."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from coworker.secrets import SecretStore


def _drive_rows(secret_path: Path) -> list[dict]:
    rows = SecretStore(path=secret_path).status()
    return [
        row
        for row in rows
        if str(row.get("profile") or "") == "google_drive"
        or str(row.get("profile") or "").startswith("google_drive:")
    ]


def resolve_candidate_state_dirs(users_root: Path) -> tuple[list[Path], int]:
    readable: list[Path] = []
    inspected = 0
    if not users_root.is_dir():
        return readable, inspected
    for user_dir in sorted(users_root.iterdir(), key=lambda p: p.name.casefold()):
        secret_path = user_dir / "AppData" / "Roaming" / "coworker" / "secrets.json"
        if not secret_path.is_file():
            continue
        inspected += 1
        try:
            rows = _drive_rows(secret_path)
        except Exception:
            continue
        if any(not bool(row.get("expired")) for row in rows):
            readable.append(secret_path.parent.resolve())
    return readable, inspected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users-root", default=r"C:\Users")
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    matches, inspected = resolve_candidate_state_dirs(Path(args.users_root))
    result = {
        "schema_version": "openworker-drive-credential-store-probe/v1",
        "inspected_secret_files": inspected,
        "readable_active_drive_stores": len(matches),
        "ambiguous": len(matches) > 1,
    }
    print(json.dumps(result, sort_keys=True))

    encoded = ""
    if len(matches) == 1:
        encoded = base64.b64encode(str(matches[0]).encode("utf-8")).decode("ascii")
    if args.github_output:
        output = Path(args.github_output)
        with output.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"state_dir_b64={encoded}\n")
            fh.write(f"match_count={len(matches)}\n")
            fh.write(f"inspected_count={inspected}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
