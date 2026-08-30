from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from coworker.engineering.source_ingress import EngineeringSourceIngress, SourceIngressError
from coworker.runtimes.job_binding import JobBindingStore

SCHEMA = "openworker.source-ingress-request.v1"


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(ch in "0123456789abcdef" for ch in value)


def load_request(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SourceIngressError(f"cannot read source ingress request: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise SourceIngressError("unsupported source ingress request schema")
    required = (
        "source_blob_repository",
        "original_name",
        "canonical_name",
        "expected_size",
        "expected_sha256",
        "media_type",
        "workspace_root",
        "assigned_host",
        "user_request",
    )
    for name in required:
        if not str(data.get(name, "")).strip():
            raise SourceIngressError(f"missing source ingress field: {name}")
    try:
        data["expected_size"] = int(data["expected_size"])
    except (TypeError, ValueError) as exc:
        raise SourceIngressError("expected_size must be an integer") from exc
    if data["expected_size"] <= 0:
        raise SourceIngressError("expected_size must be positive")
    digest = str(data["expected_sha256"]).strip().lower()
    if not _is_hex(digest, 64):
        raise SourceIngressError("expected_sha256 must be 64 hexadecimal characters")
    data["expected_sha256"] = digest

    one = str(data.get("source_blob_sha", "") or "").strip().lower()
    many_raw = data.get("source_blob_shas", [])
    if many_raw is None:
        many_raw = []
    if not isinstance(many_raw, list):
        raise SourceIngressError("source_blob_shas must be an array")
    many = [str(item or "").strip().lower() for item in many_raw]
    if one and many:
        raise SourceIngressError("use source_blob_sha or source_blob_shas, not both")
    if not one and not many:
        raise SourceIngressError("source_blob_sha or source_blob_shas is required")
    if one and not _is_hex(one, 40):
        raise SourceIngressError("source_blob_sha must be a 40-character Git SHA-1")
    if many:
        if len(many) > 512:
            raise SourceIngressError("source_blob_shas exceeds 512 chunks")
        if any(not _is_hex(item, 40) for item in many):
            raise SourceIngressError("every source_blob_shas item must be a 40-character Git SHA-1")
        if len(set(many)) != len(many):
            raise SourceIngressError("source_blob_shas contains duplicate chunk references")
    data["source_blob_sha"] = one
    data["source_blob_shas"] = many

    compression = str(data.get("source_compression", "none") or "none").strip().lower()
    if compression not in {"none", "xz"}:
        raise SourceIngressError("source_compression must be none or xz")
    data["source_compression"] = compression
    packed_sha = str(data.get("packed_sha256", "") or "").strip().lower()
    if packed_sha and not _is_hex(packed_sha, 64):
        raise SourceIngressError("packed_sha256 must be 64 hexadecimal characters")
    data["packed_sha256"] = packed_sha
    packed_size = data.get("packed_size")
    if packed_size not in (None, ""):
        try:
            packed_size = int(packed_size)
        except (TypeError, ValueError) as exc:
            raise SourceIngressError("packed_size must be an integer") from exc
        if packed_size <= 0:
            raise SourceIngressError("packed_size must be positive")
    data["packed_size"] = packed_size
    return data


def host_gate(assigned_host: str) -> str:
    actual = JobBindingStore.current_host().strip()
    if not actual:
        raise SourceIngressError("cannot determine current runner host")
    if actual.casefold() != assigned_host.casefold():
        raise SourceIngressError(f"wrong self-hosted machine: expected {assigned_host}, got {actual}")
    return actual


def _fetch_blob(repo: str, sha: str, token: str) -> bytes:
    url = f"https://api.github.com/repos/{repo}/git/blobs/{sha}"
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "openworker-engineering-source-ingress",
    }
    try:
        response = httpx.get(url, headers=headers, timeout=60.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise SourceIngressError(f"private source blob download failed for {sha}: {exc}") from exc
    if response.is_error:
        raise SourceIngressError(f"private source blob download failed for {sha} ({response.status_code})")
    return response.content


def fetch_private_source(request: dict[str, Any], token: str, staging: Path) -> None:
    token = str(token or "").strip()
    if not token:
        raise SourceIngressError("GH_TOKEN is required to fetch the private source blob")
    repo = str(request["source_blob_repository"]).strip()
    shas = request["source_blob_shas"] or [request["source_blob_sha"]]
    packed = b"".join(_fetch_blob(repo, sha, token) for sha in shas)
    packed_size = request.get("packed_size")
    if packed_size is not None and len(packed) != packed_size:
        raise SourceIngressError(f"packed source size mismatch: expected {packed_size}, got {len(packed)}")
    packed_sha = request.get("packed_sha256", "")
    actual_packed_sha = hashlib.sha256(packed).hexdigest()
    if packed_sha and actual_packed_sha != packed_sha:
        raise SourceIngressError(
            f"packed source SHA256 mismatch: expected {packed_sha}, got {actual_packed_sha}"
        )
    if request["source_compression"] == "xz":
        try:
            source = lzma.decompress(packed, format=lzma.FORMAT_XZ)
        except lzma.LZMAError as exc:
            raise SourceIngressError(f"cannot decompress XZ source bundle: {exc}") from exc
    else:
        source = packed
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_bytes(source)
    size = len(source)
    digest = hashlib.sha256(source).hexdigest()
    if size != int(request["expected_size"]):
        raise SourceIngressError(
            f"staged source size mismatch: expected {request['expected_size']}, got {size}"
        )
    if digest != request["expected_sha256"]:
        raise SourceIngressError(
            f"staged source SHA256 mismatch: expected {request['expected_sha256']}, got {digest}"
        )
    expected_header = str(request.get("expected_header", "") or "").strip()
    if expected_header:
        header = source[:32].decode("ascii", errors="replace").rstrip("\x00")
        if not header.startswith(expected_header):
            raise SourceIngressError(
                f"staged source header mismatch: expected prefix {expected_header!r}, got {header!r}"
            )


def wait_health(base_url: str, process: subprocess.Popen[bytes], stderr_path: Path, timeout_s: int = 240) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if process.poll() is not None:
            detail = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
            raise SourceIngressError(
                f"AI-Engineering-OS exited before health became ready: {process.returncode}\n{detail[-4000:]}"
            )
        try:
            response = httpx.get(base_url + "/healthz", timeout=3.0)
            if response.status_code == 200 and response.json().get("status") == "ok":
                return
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2)
    raise SourceIngressError("AI-Engineering-OS did not become healthy within timeout")


def start_isolated_os(os_root: Path, workspace: Path, port: int) -> tuple[subprocess.Popen[bytes], str, Path, Path]:
    os_root = os_root.resolve()
    if not (os_root / "go.mod").is_file():
        raise SourceIngressError(f"AI-Engineering-OS checkout is invalid: {os_root}")
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = workspace / ".engineering-os"
    job_root = state_root / "jobs"
    logs = state_root / "logs"
    job_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    stdout_path = logs / f"source-ingress-{run_id}.stdout.log"
    stderr_path = logs / f"source-ingress-{run_id}.stderr.log"
    env = os.environ.copy()
    env.update(
        {
            "ENGINEERING_OS_ADDRESS": f"127.0.0.1:{port}",
            "ENGINEERING_OS_DB_PATH": str(state_root / "engineering-os.db"),
            "ENGINEERING_OS_JOB_ROOT": str(job_root),
            "ENGINEERING_OS_WORKSPACE_ROOT": str(workspace),
            "ENGINEERING_OS_MODULES_LOCK": str(os_root / "modules.lock.yaml"),
        }
    )
    stdout_handle = stdout_path.open("wb")
    stderr_handle = stderr_path.open("wb")
    try:
        process = subprocess.Popen(
            ["go", "run", "./cmd/engineering-os"],
            cwd=os_root,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
    except Exception:
        stdout_handle.close()
        stderr_handle.close()
        raise
    stdout_handle.close()
    stderr_handle.close()
    base_url = f"http://127.0.0.1:{port}"
    wait_health(base_url, process, stderr_path)
    return process, base_url, stdout_path, stderr_path


def write_github_outputs(result: dict[str, Any], evidence_path: Path) -> None:
    output = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        for key in ("project_id", "job_id", "canonical_path", "sha256", "os_artifact_id"):
            handle.write(f"{key}={result.get(key, '')}\n")
        handle.write(f"evidence_path={evidence_path}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run governed OpenWorker engineering source ingress")
    parser.add_argument("--request", required=True)
    parser.add_argument("--os-root", required=True)
    parser.add_argument("--source-token-env", default="GH_TOKEN")
    parser.add_argument("--port", type=int, default=18084)
    args = parser.parse_args()

    request = load_request(Path(args.request).resolve())
    actual_host = host_gate(str(request["assigned_host"]))
    workspace = Path(str(request["workspace_root"])).expanduser().resolve()
    staging = Path(os.environ.get("RUNNER_TEMP", str(workspace / ".staging"))) / "openworker-engineering-source.bin"
    fetch_private_source(request, os.environ.get(args.source_token_env, ""), staging)
    process: subprocess.Popen[bytes] | None = None
    try:
        process, os_url, stdout_path, stderr_path = start_isolated_os(
            Path(args.os_root), workspace, args.port
        )
        ingress = EngineeringSourceIngress(
            os_url=os_url,
            workspace=workspace,
            assigned_host=str(request["assigned_host"]),
            user_request=str(request["user_request"]),
        )
        try:
            result = ingress.ingest(
                staging,
                canonical_name=str(request["canonical_name"]),
                original_name=str(request["original_name"]),
                media_type=str(request["media_type"]),
                expected_size=int(request["expected_size"]),
                expected_sha256=str(request["expected_sha256"]),
                expected_header=str(request.get("expected_header", "") or ""),
                source_run_id=os.environ.get("GITHUB_RUN_ID", ""),
                producer_repository=os.environ.get("GITHUB_REPOSITORY", ""),
                producer_commit_sha=os.environ.get("GITHUB_SHA", ""),
            )
        finally:
            ingress.close()
        payload = result.as_dict()
        payload["runner_name"] = os.environ.get("RUNNER_NAME", "")
        payload["github_run_id"] = os.environ.get("GITHUB_RUN_ID", "")
        payload["producer_commit_sha"] = os.environ.get("GITHUB_SHA", "")
        payload["transport"] = {
            "repository": request["source_blob_repository"],
            "blob_count": len(request["source_blob_shas"] or [request["source_blob_sha"]]),
            "compression": request["source_compression"],
            "packed_size": request.get("packed_size"),
            "packed_sha256": request.get("packed_sha256", ""),
        }
        payload["os_stdout"] = str(stdout_path)
        payload["os_stderr"] = str(stderr_path)
        evidence_root = workspace / "evidence" / "source-ingress"
        evidence_root.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_root / f"run-{os.environ.get('GITHUB_RUN_ID', 'local')}.json"
        temp = evidence_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, evidence_path)
        canonical = Path(result.canonical_path)
        if not canonical.is_file() or canonical.stat().st_size != int(request["expected_size"]):
            raise SourceIngressError("canonical source failed final physical size gate")
        if hashlib.sha256(canonical.read_bytes()).hexdigest() != request["expected_sha256"]:
            raise SourceIngressError("canonical source failed final physical SHA256 gate")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(
            "SOURCE_INGRESS_REAL_PASS "
            f"host={actual_host} project={result.project_id} job={result.job_id} "
            f"artifact={result.os_artifact_id} path={canonical} size={canonical.stat().st_size} "
            f"sha256={result.sha256}"
        )
        write_github_outputs(payload, evidence_path)
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SourceIngressError as exc:
        print(f"SOURCE_INGRESS_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
