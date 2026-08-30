from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

from coworker.engineering.engineering_os import EngineeringOSClient, EngineeringOSConfig
from scripts.engineering_source_ingress_action import start_isolated_os

PROJECT_CODE = "CASE0005-SNOW-WHITE"
JOB_CODE = "CASE0005-FINAL-DELIVERY"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def post_project(base_url: str) -> dict[str, Any]:
    response = httpx.post(
        base_url + "/api/v1/projects",
        json={
            "code": PROJECT_CODE,
            "name": "Case 0005 Snow White",
            "description": "Snow White short-film final artifact lifecycle",
            "metadata": {"case_id": "0005", "execution_route": "local_supervisor"},
        },
        timeout=30.0,
    )
    if response.status_code == 409:
        return {}
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("Engineering OS create project response is not an object")
    return value


def find_by_code(items: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
    matches = [item for item in items if str(item.get("code") or "").strip().casefold() == code.casefold()]
    if len(matches) > 1:
        raise RuntimeError(f"Engineering OS identity conflict: more than one object has code {code}")
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--os-root", required=True)
    parser.add_argument("--evidence", default=".openworker/engineering-os-identity.json")
    parser.add_argument("--port", type=int, default=18087)
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    os_root = Path(args.os_root).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace unavailable: {workspace}")
    if not (os_root / "go.mod").is_file():
        raise RuntimeError(f"Engineering OS checkout invalid: {os_root}")
    evidence = (workspace / args.evidence).resolve()
    try:
        evidence.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError("identity evidence escapes workspace") from exc

    process = None
    try:
        process, base_url, stdout_path, stderr_path = start_isolated_os(os_root, workspace, args.port)
        client = EngineeringOSClient(EngineeringOSConfig(base_url=base_url, timeout_seconds=30.0))

        project = find_by_code(client.list_projects(), PROJECT_CODE)
        project_created = False
        if project is None:
            created = post_project(base_url)
            project_created = bool(created)
            project = created or find_by_code(client.list_projects(), PROJECT_CODE)
        if not isinstance(project, dict):
            raise RuntimeError("Engineering OS project could not be created or resolved")
        project_id = str(project.get("id") or "").strip()
        if not project_id:
            raise RuntimeError("Engineering OS project has no id")

        job = find_by_code(client.list_jobs(project_id=project_id), JOB_CODE)
        job_created = False
        if job is None:
            try:
                job = client.create_job(
                    project_id=project_id,
                    code=JOB_CODE,
                    name="Case 0005 final Snow White delivery",
                    user_request="Register, review and deliver the canonical Snow White final MP4.",
                    expected_deliverables=["final_mp4"],
                    metadata={"case_id": "0005", "execution_route": "local_supervisor"},
                )
                job_created = True
            except Exception:
                # Code-conflict races are resolved by rereading the authoritative DB.
                job = find_by_code(client.list_jobs(project_id=project_id), JOB_CODE)
                if job is None:
                    raise
        job_id = str(job.get("id") or "").strip()
        if not job_id:
            raise RuntimeError("Engineering OS job has no id")

        # Re-read both identities from authoritative APIs after any create path.
        project_check = client.get_project(project_id)
        job_check = client.get_job(job_id)
        if str(project_check.get("code") or "").strip() != PROJECT_CODE:
            raise RuntimeError("Engineering OS project code mismatch after reread")
        if str(job_check.get("code") or "").strip() != JOB_CODE:
            raise RuntimeError("Engineering OS job code mismatch after reread")
        if str(job_check.get("project_id") or "").strip() != project_id:
            raise RuntimeError("Engineering OS job/project identity mismatch")

        output = {
            "schema_version": "openworker-case0005-engineering-os-identity/v1",
            "case_id": "0005",
            "project_code": PROJECT_CODE,
            "project_id": project_id,
            "job_code": JOB_CODE,
            "job_id": job_id,
            "project_created": project_created,
            "job_created": job_created,
            "engineering_os_db": str(workspace / ".engineering-os" / "engineering-os.db"),
            "execution_route": "local_supervisor",
            "github_action_used_for_business_execution": False,
            "os_stdout": str(stdout_path),
            "os_stderr": str(stderr_path),
        }
        atomic_json(evidence, output)
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except Exception:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
