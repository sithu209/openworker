"""Case 0002 adapter for the OpenWorker Local Supervisor.

This is intentionally thin: llama.cpp reasons, go-tool explains registered tools,
and OpenWorker remains durable execution authority.  No second scheduler lives
here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

from .case_worklist_runtime import CaseWorklistRuntime
from .local_supervisor import (
    SUPERVISOR_SYSTEM_CONTRACT,
    LocalSupervisorConfig,
    LocalSupervisorHost,
    ToolDispatchError,
    _json_schema,
    _require,
    _tool,
    build_tool_specs,
)

CASE2_POLICY = """Case 0002 (Aladdin) execution policy:
- Read the durable CaseWorklist before selecting any business action.
- Ask go-tool /agent/query before choosing a tool/capability. Never guess a workflow or canonical input.
- Obey canonical_next_step_id, dependencies, allowed_actions, acceptance, workspace_root and assigned_host.
- For step 0002-025 the intended product is a storyboard PPTX WITHOUT images. Stop at 0002-027 for user approval after a real artifact/receipt is accepted.
- Do not generate IMAGE or VIDEO before the corresponding approval gate.
- Action/dispatch acceptance is transport evidence only. Business success requires the durable case evidence and artifact/QC contract.
"""


class Case2LocalSupervisorHost(LocalSupervisorHost):
    def __init__(self, config: LocalSupervisorConfig, *, workspace_root: str = r"D:\AI-Example\0002", go_tool_url: str = "http://127.0.0.1:8848", **kwargs: Any) -> None:
        super().__init__(config, **kwargs)
        self.workspace_root = str(Path(workspace_root))
        self.go_tool_url = go_tool_url.rstrip("/")

    def _go(self, method: str, path: str, **kwargs: Any) -> Any:
        with httpx.Client(base_url=self.go_tool_url, timeout=30.0) as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

    def case2_tool_specs(self) -> list[dict[str, Any]]:
        string = {"type": "string"}
        return build_tool_specs() + [
            _tool("case_worklist_current", "Read Case 0002 durable worklist from the assigned workspace.", _json_schema({})),
            _tool(
                "go_tool_query",
                "Ask go-tool for authoritative tool/capability/action guidance before selecting a business action.",
                _json_schema({"question": string, "task": string}, ["question"]),
            ),
            _tool(
                "go_tool_capability",
                "Read one registered go-tool execution capability including owning repo, workflow, canonical inputs and failure guard decision.",
                _json_schema({"capability_id": string}, ["capability_id"]),
            ),
            _tool("go_tool_execution_readiness", "Read go-tool GitHub execution-provider credential/readiness state.", _json_schema({})),
            _tool(
                "go_tool_dispatch",
                "Dispatch ONLY a registered capability after case worklist + go_tool_query + capability detail have established it is allowed. The request is forwarded to go-tool, which fail-closes on unknown capability and negative knowledge.",
                _json_schema({"request": {"type": "object", "additionalProperties": True}}, ["request"]),
            ),
            _tool(
                "go_tool_execution_status",
                "Read a go-tool execution status by execution_id. This is transport/action status, not CaseWorklist success.",
                _json_schema({"execution_id": string}, ["execution_id"]),
            ),
        ]

    def dispatch_tool(self, name: str, raw_arguments: str | dict[str, Any] | None) -> Any:
        if isinstance(raw_arguments, dict):
            args = raw_arguments
        else:
            try:
                args = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ToolDispatchError(f"malformed JSON arguments for {name}: {exc}") from exc
        if not isinstance(args, dict):
            raise ToolDispatchError(f"tool arguments must be object for {name}")

        if name == "case_worklist_current":
            return CaseWorklistRuntime(self.workspace_root).load().as_dict()
        if name == "go_tool_query":
            body = {
                "session_id": self.session_id,
                "project": "openworker-case-0002",
                "workspace_root": self.workspace_root,
                "question": _require(args, "question"),
                "task": str(args.get("task", "case 0002 canonical next step")),
            }
            return self._go("POST", "/agent/query", json=body)
        if name == "go_tool_capability":
            cap = _require(args, "capability_id")
            return self._go("GET", f"/api/execution/capabilities/{cap}")
        if name == "go_tool_execution_readiness":
            return self._go("GET", "/api/execution/readiness")
        if name == "go_tool_dispatch":
            request = args.get("request")
            if not isinstance(request, dict):
                raise ToolDispatchError("go_tool_dispatch requires object field 'request'")
            capability_id = str(request.get("capability_id", "")).strip()
            if not capability_id:
                raise ToolDispatchError("go_tool_dispatch request.capability_id required")
            worklist = CaseWorklistRuntime(self.workspace_root).load().as_dict()
            next_id = str(worklist.get("canonical_next_step_id") or "")
            steps = worklist.get("steps") or []
            current = next((s for s in steps if str(s.get("step_id")) == next_id), None)
            allowed = set((current or {}).get("allowed_actions") or [])
            if capability_id not in allowed:
                raise ToolDispatchError(f"capability {capability_id!r} not allowed by canonical step {next_id!r}; allowed={sorted(allowed)}")
            return self._go("POST", "/api/execution/dispatch", json=request)
        if name == "go_tool_execution_status":
            eid = _require(args, "execution_id")
            return self._go("GET", f"/api/execution/runs/{eid}")
        return super().dispatch_tool(name, args)

    def run_case2_turn(self, user_message: str) -> str:
        if not self._bootstrapped:
            bootstrap = self.bootstrap("Continue Case 0002 from durable canonical next step")
        else:
            bootstrap = {
                "recovered": self.node.supervisor_snapshot(self.config.supervisor_id),
                "attention": self.node.supervisor_attention(self.config.supervisor_id),
            }
        worklist = CaseWorklistRuntime(self.workspace_root).load().as_dict()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SUPERVISOR_SYSTEM_CONTRACT + "\n" + CASE2_POLICY},
            {"role": "system", "content": "Bootstrap facts are informational only; query tools for current authority.\n" + json.dumps({"supervisor": bootstrap, "case_worklist": worklist}, ensure_ascii=False, default=str)},
            {"role": "user", "content": user_message},
        ]
        tools = self.case2_tool_specs()
        for _ in range(self.config.max_tool_rounds):
            self.maybe_heartbeat("Continue Case 0002 from durable canonical next step")
            response = self.llm.chat.completions.create(model=self.config.model, messages=messages, tools=tools, tool_choice="auto")
            message = response.choices[0].message
            messages.append(self._assistant_message_dict(message))
            calls = list(message.tool_calls or [])
            if not calls:
                return message.content or ""
            for call in calls:
                try:
                    result = {"ok": True, "result": self.dispatch_tool(call.function.name, call.function.arguments)}
                except Exception as exc:
                    result = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
        raise RuntimeError(f"max tool rounds exceeded: {self.config.max_tool_rounds}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run Case 0002 through the OpenWorker llama.cpp Local Supervisor")
    p.add_argument("--base-url", default=os.environ.get("OPENWORKER_LLAMA_BASE_URL", "http://127.0.0.1:8080/v1"))
    p.add_argument("--model", default=os.environ.get("OPENWORKER_LLAMA_MODEL", "local-coder"))
    p.add_argument("--supervisor-id", default=os.environ.get("OPENWORKER_SUPERVISOR_ID", "ODA-CODER-01"))
    p.add_argument("--openworker-url", default=os.environ.get("OPENWORKER_NODE_URL", "http://127.0.0.1:8787"))
    p.add_argument("--go-tool-url", default=os.environ.get("GO_TOOL_URL", "http://127.0.0.1:8848"))
    p.add_argument("--workspace-root", default=os.environ.get("CASE0002_WORKSPACE", r"D:\AI-Example\0002"))
    p.add_argument("--message", default="Continue Case 0002. Read durable worklist, ask go-tool, and execute only the canonical next allowed action. If 0002-025 succeeds, stop at user approval 0002-027.")
    ns = p.parse_args(argv)
    cfg = LocalSupervisorConfig(base_url=ns.base_url, model=ns.model, supervisor_id=ns.supervisor_id, openworker_url=ns.openworker_url)
    host = Case2LocalSupervisorHost(cfg, workspace_root=ns.workspace_root, go_tool_url=ns.go_tool_url)
    print(host.run_case2_turn(ns.message))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
