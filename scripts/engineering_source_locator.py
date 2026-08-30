from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "openworker.source-locator-request.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_request(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise RuntimeError("unsupported source locator request schema")
    for key in ("assigned_host", "expected_size", "expected_sha256", "expected_header"):
        if key not in data:
            raise RuntimeError(f"missing source locator field: {key}")
    candidate_paths = data.get("candidate_paths", []) or []
    search_roots = data.get("search_roots", []) or []
    name_patterns = data.get("name_patterns", []) or []
    if not isinstance(candidate_paths, list) or len(candidate_paths) > 64:
        raise RuntimeError("candidate_paths must be an array with at most 64 entries")
    if not isinstance(search_roots, list) or len(search_roots) > 16:
        raise RuntimeError("search_roots must be an array with at most 16 entries")
    if not isinstance(name_patterns, list) or len(name_patterns) > 16:
        raise RuntimeError("name_patterns must be an array with at most 16 entries")
    if not candidate_paths and not search_roots:
        raise RuntimeError("candidate_paths or search_roots is required")
    if search_roots and not name_patterns:
        raise RuntimeError("name_patterns is required when search_roots is used")
    data["candidate_paths"] = [str(v) for v in candidate_paths if str(v).strip()]
    data["search_roots"] = [str(v) for v in search_roots if str(v).strip()]
    data["name_patterns"] = [str(v) for v in name_patterns if str(v).strip()]
    data["max_depth"] = int(data.get("max_depth", 8))
    data["max_size_matches"] = int(data.get("max_size_matches", 256))
    data["prefer_existing_canonical"] = bool(data.get("prefer_existing_canonical", False))
    if data["max_depth"] < 0 or data["max_depth"] > 20:
        raise RuntimeError("max_depth must be between 0 and 20")
    if data["max_size_matches"] <= 0 or data["max_size_matches"] > 4096:
        raise RuntimeError("max_size_matches must be between 1 and 4096")
    data["expected_size"] = int(data["expected_size"])
    if data["expected_size"] <= 0:
        raise RuntimeError("expected_size must be positive")
    digest = str(data["expected_sha256"]).strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise RuntimeError("expected_sha256 must be 64 hexadecimal characters")
    data["expected_sha256"] = digest
    return data


def current_host() -> str:
    for key in ("COMPUTERNAME", "HOSTNAME"):
        value = str(os.environ.get(key, "") or "").strip()
        if value:
            return value
    return ""


def expand_candidates(raw: str) -> list[Path]:
    text = os.path.expandvars(str(raw or "").strip())
    if not text:
        return []
    path = Path(text)
    if any(ch in text for ch in "*?["):
        parent = path.parent
        pattern = path.name
        if not parent.is_dir():
            return []
        return sorted(p.resolve() for p in parent.glob(pattern) if p.is_file())
    return [path.resolve()] if path.is_file() else []


def bounded_recursive_candidates(
    roots: Iterable[str],
    patterns: list[str],
    *,
    expected_size: int,
    max_depth: int,
    max_size_matches: int,
) -> tuple[list[Path], list[dict[str, Any]]]:
    found: list[Path] = []
    roots_evidence: list[dict[str, Any]] = []
    for raw_root in roots:
        root = Path(os.path.expandvars(str(raw_root))).expanduser()
        root_entry: dict[str, Any] = {
            "root": str(root),
            "exists": root.is_dir(),
            "name_match_count": 0,
            "size_match_count": 0,
            "stat_error_count": 0,
            "truncated": False,
        }
        roots_evidence.append(root_entry)
        if not root.is_dir():
            continue
        root = root.resolve()
        root_parts = len(root.parts)
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.parts) - root_parts
            if depth >= max_depth:
                dirs[:] = []
            dirs[:] = [
                d for d in dirs
                if d.casefold() not in {".git", "node_modules", ".venv", "venv", "__pycache__", "_work"}
            ]
            for name in files:
                if not any(fnmatch.fnmatch(name.casefold(), pattern.casefold()) for pattern in patterns):
                    continue
                root_entry["name_match_count"] += 1
                path = (current_path / name).resolve()
                try:
                    if path.stat().st_size != expected_size:
                        continue
                except (OSError, PermissionError):
                    root_entry["stat_error_count"] += 1
                    continue
                root_entry["size_match_count"] += 1
                found.append(path)
                if len(found) >= max_size_matches:
                    root_entry["truncated"] = True
                    return found, roots_evidence
    return found, roots_evidence


def inspect(path: Path, expected_size: int) -> dict[str, Any]:
    size = path.stat().st_size
    item: dict[str, Any] = {
        "path": str(path),
        "size": size,
        "size_match": size == expected_size,
        "sha256": "",
        "header": "",
    }
    if size != expected_size:
        item["sha256_match"] = False
        item["header_match"] = False
        return item
    item["sha256"] = sha256_file(path)
    with path.open("rb") as handle:
        item["header"] = handle.read(32).decode("ascii", errors="replace").rstrip("\x00")
    return item


def exact_match(item: dict[str, Any], expected_sha: str, expected_header: str) -> bool:
    if not item.get("size_match"):
        return False
    item["sha256_match"] = item.get("sha256") == expected_sha
    item["header_match"] = (not expected_header) or str(item.get("header", "")).startswith(expected_header)
    return bool(item["sha256_match"] and item["header_match"])


def canonical_workspace_match(
    request: dict[str, Any], expected_size: int, expected_sha: str, expected_header: str
) -> dict[str, Any] | None:
    if not request.get("prefer_existing_canonical"):
        return None
    workspace = str(request.get("workspace_root", "") or "").strip()
    canonical_name = str(request.get("canonical_name", "") or "").strip()
    if not workspace or not canonical_name:
        raise RuntimeError("prefer_existing_canonical requires workspace_root and canonical_name")
    path = (Path(workspace).expanduser().resolve() / "input" / canonical_name).resolve()
    if not path.is_file():
        return None
    item = inspect(path, expected_size)
    if not exact_match(item, expected_sha, expected_header):
        raise RuntimeError(f"existing canonical source identity mismatch: {path}")
    item["authority"] = "canonical_workspace"
    return item


def write_evidence(result: dict[str, Any], evidence: Path) -> None:
    evidence.parent.mkdir(parents=True, exist_ok=True)
    temp = evidence.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, evidence)


def publish_outputs(source_path: str, evidence: Path) -> None:
    output = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"source_path={source_path}\n")
            handle.write(f"evidence_path={evidence}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    request = load_request(Path(args.request).resolve())
    host = current_host()
    assigned = str(request["assigned_host"]).strip()
    if not host or host.casefold() != assigned.casefold():
        raise RuntimeError(f"wrong self-hosted machine: expected {assigned}, got {host or '<unknown>'}")

    expected_size = int(request["expected_size"])
    expected_sha = request["expected_sha256"]
    expected_header = str(request.get("expected_header", "") or "").strip()
    evidence = Path(args.evidence).resolve()

    canonical = canonical_workspace_match(request, expected_size, expected_sha, expected_header)
    if canonical is not None:
        result = {
            "schema_version": "openworker.source-locator-evidence.v4",
            "assigned_host": assigned,
            "actual_host": host,
            "expected_size": expected_size,
            "expected_sha256": expected_sha,
            "expected_header": expected_header,
            "authority": "canonical_workspace",
            "physical_checked_count": 1,
            "checked": [canonical],
            "matched": True,
            "source_path": canonical["path"],
        }
        write_evidence(result, evidence)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"SOURCE_LOCATOR_CANONICAL_MATCH path={canonical['path']} sha256={expected_sha}")
        publish_outputs(canonical["path"], evidence)
        return 0

    checked: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    discovered, roots_evidence = bounded_recursive_candidates(
        request["search_roots"],
        request["name_patterns"],
        expected_size=expected_size,
        max_depth=request["max_depth"],
        max_size_matches=request["max_size_matches"],
    )
    paths: list[Path] = []
    for candidate in request["candidate_paths"]:
        paths.extend(expand_candidates(str(candidate)))
    paths.extend(discovered)

    for path in paths:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        try:
            item = inspect(path, expected_size)
        except (OSError, PermissionError) as exc:
            checked.append({"path": str(path), "error": str(exc)})
            continue
        if exact_match(item, expected_sha, expected_header):
            matches.append(item)
        checked.append(item)

    if len(matches) > 1:
        unique_paths = {os.path.normcase(item["path"]) for item in matches}
        if len(unique_paths) > 1:
            raise RuntimeError(f"ambiguous exact source: {len(matches)} matching files")
    result = {
        "schema_version": "openworker.source-locator-evidence.v4",
        "assigned_host": assigned,
        "actual_host": host,
        "expected_size": expected_size,
        "expected_sha256": expected_sha,
        "expected_header": expected_header,
        "authority": "discovered_source" if matches else "",
        "candidate_count": len(request["candidate_paths"]),
        "search_root_count": len(request["search_roots"]),
        "name_patterns": request["name_patterns"],
        "search_roots": roots_evidence,
        "physical_checked_count": len(checked),
        "checked": checked,
        "matched": bool(matches),
        "source_path": matches[0]["path"] if matches else "",
    }
    write_evidence(result, evidence)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if matches:
        print(f"SOURCE_LOCATOR_EXACT_MATCH path={matches[0]['path']} sha256={expected_sha}")
        publish_outputs(matches[0]["path"], evidence)
        return 0
    print("SOURCE_LOCATOR_NO_MATCH", file=sys.stderr)
    return 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SOURCE_LOCATOR_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
