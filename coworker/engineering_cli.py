"""Thin CLI for the EngineeringHarnessHost.

In normal mode this is an interactive OpenWorker engineering Harness session.
In Action mode the self-hosted GitHub Action remains the execution boundary:
DeepSeek Harness may only call explicitly allowlisted engineering tools, and all
runtime evidence is appended to the OpenWorker project knowledge ledger.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from .engine import ApprovalOutcome, PermissionRequest
from .events import Event, EventType
from .permissions import Mode
from .runtimes.engineering_host import EngineeringHarnessHost
from .runtimes.engineering_launch import packaged_process_config
from .runtimes.project_knowledge import ProjectKnowledgeStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openworker-engineering", description="Run one OpenWorker engineering Harness session from a Project Workspace")
    parser.add_argument("request", nargs="*", help="User request. When omitted, read TASK.md only.")
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument("--engineering-os-url", default="")
    parser.add_argument("--tool-runtime-url", default="")
    parser.add_argument("--component-id", default="")
    parser.add_argument("--allow-publish", action="store_true", help="Enable the AI-Engineering-OS publish capability. Each consequential call still requires OpenWorker approval.")
    parser.add_argument("--auto-approve", action="store_true", help="Interactive/testing compatibility: approve consequential engineering calls for this CLI session.")
    parser.add_argument("--action-mode", action="store_true", help="Self-hosted Action mode. Requires one or more exact --allow-tool entries and denies every other consequential tool.")
    parser.add_argument("--allow-tool", action="append", default=[], help="Exact engineering tool name allowed in --action-mode. Repeat for multiple tools.")
    parser.add_argument("--json-events", action="store_true")
    return parser


def _resolve_request(workspace: Path, parts: list[str]) -> str:
    direct = " ".join(parts).strip()
    if direct:
        return direct
    task = workspace / "TASK.md"
    if not task.is_file():
        raise SystemExit("No request supplied and Project Workspace has no TASK.md")
    text = task.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("TASK.md is empty")
    return text


async def _interactive_approver(request: PermissionRequest) -> ApprovalOutcome:
    summary = json.dumps(request.arguments, ensure_ascii=False, default=str)
    prompt = f"Approve {request.tool_name} {summary}? [y/N/a(always tool)] "
    answer = (await asyncio.to_thread(input, prompt)).strip().lower()
    if answer in {"y", "yes"}: return ApprovalOutcome.ONCE
    if answer in {"a", "always"}: return ApprovalOutcome.ALWAYS_TOOL
    return ApprovalOutcome.DENY


async def _approve_once(_request: PermissionRequest) -> ApprovalOutcome:
    return ApprovalOutcome.ONCE


def _action_approver(allowed: set[str]):
    async def approve(request: PermissionRequest) -> ApprovalOutcome:
        return ApprovalOutcome.ONCE if request.tool_name in allowed else ApprovalOutcome.DENY
    return approve


def _safe_details(data: dict[str, Any]) -> dict[str, Any]:
    """Keep the ledger JSON-safe and bounded; raw large tool output belongs in evidence files."""
    safe: dict[str, Any] = {}
    for key, value in data.items():
        if key in {"content", "text"} and isinstance(value, str) and len(value) > 2000:
            safe[key] = value[:2000] + "…"
        else:
            try:
                json.dumps(value)
                safe[key] = value
            except (TypeError, ValueError):
                safe[key] = str(value)
    return safe


def _record_event(store: ProjectKnowledgeStore, event: Event) -> None:
    data = dict(event.data or {})
    runtime = str(data.get("runtime") or "")
    session_id = str(data.get("session_id") or "")
    runtime_job_id = str(data.get("runtime_job_id") or "")
    execution_id = str(data.get("execution_id") or "")
    prompt_id = str(data.get("prompt_id") or "")
    tool_name = str(data.get("tool_name") or data.get("name") or "")
    if event.type is EventType.TURN_START:
        store.record(kind="dispatch", stage="harness-turn", status="running", summary="DeepSeek Harness turn started inside self-hosted Action", owner="OpenWorker", evidence=(f"session_id={session_id}", f"runtime_job_id={runtime_job_id}"), runtime=runtime or "engineering-harness", session_id=session_id, runtime_job_id=runtime_job_id, details=_safe_details(data))
    elif event.type is EventType.TOOL_STARTED:
        store.record(kind="tool-start", stage="harness-tool", status="running", summary=f"Harness started engineering tool {tool_name or '<unknown>'}", owner="AI-Engineering-OS", capability_id=tool_name, runtime=runtime or "engineering-harness", session_id=session_id, runtime_job_id=runtime_job_id, execution_id=execution_id, prompt_id=prompt_id, details=_safe_details(data))
    elif event.type is EventType.TOOL_FINISHED:
        store.record(kind="tool-finish", stage="harness-tool", status="completed", summary=f"Harness engineering tool finished {tool_name or '<unknown>'}", owner="AI-Engineering-OS", capability_id=tool_name, runtime=runtime or "engineering-harness", session_id=session_id, runtime_job_id=runtime_job_id, execution_id=execution_id, prompt_id=prompt_id, details=_safe_details(data))
    elif event.type is EventType.ERROR:
        error = str(data.get("error") or "Harness runtime error")
        store.record(kind="failure", stage="harness-turn", status="failed", summary=error, owner="OpenWorker", blockers=(error,), runtime=runtime or "engineering-harness", session_id=session_id, runtime_job_id=runtime_job_id, details=_safe_details(data))
    elif event.type is EventType.INTERRUPTED:
        store.record(kind="interrupted", stage="harness-turn", status="interrupted", summary="DeepSeek Harness turn interrupted", owner="OpenWorker", blockers=("runtime interrupted",), runtime=runtime or "engineering-harness", session_id=session_id, runtime_job_id=runtime_job_id, details=_safe_details(data))
    elif event.type is EventType.TURN_END:
        stop_reason = str(data.get("stop_reason") or "end_turn")
        failed = stop_reason in {"error", "bootstrap_error", "cancelled"}
        store.record(kind="completed" if not failed else "failure", stage="harness-turn", status="failed" if failed else "completed", summary=f"DeepSeek Harness turn ended: {stop_reason}", owner="OpenWorker", blockers=((f"Harness stop_reason={stop_reason}",) if failed else ()), runtime=runtime or "engineering-harness", session_id=session_id, runtime_job_id=runtime_job_id, details=_safe_details(data))


async def _run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir(): raise SystemExit(f"Project Workspace does not exist: {workspace}")
    request = _resolve_request(workspace, list(args.request))
    allowed = {str(v).strip() for v in args.allow_tool if str(v).strip()}
    if args.action_mode:
        if args.auto_approve:
            raise SystemExit("--action-mode cannot be combined with unrestricted --auto-approve")
        if not allowed:
            raise SystemExit("--action-mode requires at least one exact --allow-tool")
        approver = _action_approver(allowed)
    else:
        approver = _approve_once if args.auto_approve else _interactive_approver

    process_config = packaged_process_config(workspace)
    host = EngineeringHarnessHost(workspace=workspace, process_config=process_config, engineering_os_base_url=args.engineering_os_url or None, tool_runtime_base_url=args.tool_runtime_url or None, mode=Mode.INTERACTIVE, approver=approver, allow_publish=bool(args.allow_publish), component_id=args.component_id)
    failed = False
    store: ProjectKnowledgeStore | None = None
    try:
        async for event in host.run(request, source={"surface":"openworker-engineering-action" if args.action_mode else "openworker-engineering-cli"}):
            if store is None and host.scope is not None:
                store = ProjectKnowledgeStore(workspace)
            if store is not None:
                _record_event(store, event)
            if args.json_events:
                print(json.dumps({"type":event.type.value,"data":event.data}, ensure_ascii=False, default=str)); continue
            if event.type is EventType.ASSISTANT_MESSAGE:
                text = event.data.get("content") or event.data.get("text")
                if text: print(text)
            elif event.type is EventType.ERROR:
                failed = True; print(f"error: {event.data.get('error')}", file=sys.stderr)
            elif event.type is EventType.INTERRUPTED:
                failed = True; print("interrupted", file=sys.stderr)
        health = await host.health()
        if args.json_events: print(json.dumps({"type":"host_health","data":health}, ensure_ascii=False, default=str))
    finally:
        await host.aclose()
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try: return asyncio.run(_run(args))
    except KeyboardInterrupt: return 130


if __name__ == "__main__":
    raise SystemExit(main())