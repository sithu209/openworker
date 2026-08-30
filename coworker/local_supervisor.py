"""OpenAI-compatible llama.cpp host for the OpenWorker Local Supervisor.

The host owns only model conversation/tool dispatch. OpenWorker remains the
durable authority for jobs, processes, queue, locks, progress and recovery.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from .node_client import OpenWorkerNodeClient

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


SUPERVISOR_SYSTEM_CONTRACT = """You are an OpenWorker Local Supervisor, not a worker process and not a scheduler.
OpenWorker durable state is the only authority for jobs, queue, PID, process lifecycle, locks, progress, artifacts, and QC. Never infer execution state from your context.
Use the provided tools to observe and control work. Do not start or supervise long-running processes directly with shell, PowerShell Start-Process, or private PID tracking. Do not create another durable queue or scheduler.
A new transient supervisor session is created on each host launch and durable state is recovered before the first model request. Query tools for current authority before making assumptions.
After job_submit returns a durable ACK, do not block waiting for the long job. Continue supervising other work and observe progress later.
Action completed does not mean job succeeded. Success requires OpenWorker durable state and, when applicable, artifact/QC receipts.
Fixed-machine work must never drift to another machine. Cross-machine routing is allowed only when explicitly requested through OpenWorker cluster semantics.
For failed, timed_out, stale, or blocked work, inspect durable state and available failure/negative knowledge before retrying or replanning.
Record important decisions with supervisor_decision using decision_type/reason_code/input_state_hash/result. Never store hidden chain-of-thought.
If a tool call fails or input is malformed, do not guess that it succeeded.
"""


@dataclass(slots=True)
class LocalSupervisorConfig:
    base_url: str = "http://127.0.0.1:8080/v1"
    api_key: str = "sk-local"
    model: str = "local-coder"
    supervisor_id: str = "LOCAL-CODER-01"
    openworker_url: str = "http://127.0.0.1:8787"
    max_tool_rounds: int = 16
    heartbeat_interval_sec: float = 10.0

    @classmethod
    def from_toml(cls, path: str | Path) -> "LocalSupervisorConfig":
        defaults = cls()
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        cfg = raw.get("local_supervisor", {})
        return cls(
            base_url=str(cfg.get("base_url", defaults.base_url)),
            api_key=str(cfg.get("api_key", defaults.api_key)),
            model=str(cfg.get("model", defaults.model)),
            supervisor_id=str(cfg.get("supervisor_id", defaults.supervisor_id)),
            openworker_url=str(cfg.get("openworker_url", defaults.openworker_url)),
            max_tool_rounds=int(cfg.get("max_tool_rounds", defaults.max_tool_rounds)),
            heartbeat_interval_sec=float(cfg.get("heartbeat_interval_sec", defaults.heartbeat_interval_sec)),
        )


class ToolDispatchError(RuntimeError):
    pass


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def build_tool_specs() -> list[dict[str, Any]]:
    s = {"type": "string"}
    return [
        _tool("supervisor_snapshot", "Read durable supervisor snapshot.", {}),
        _tool("supervisor_jobs", "List durable jobs owned by this local supervisor machine.", {}),
        _tool("supervisor_attention", "Return only jobs/events requiring supervisor attention.", {}),
        _tool("supervisor_recover", "Rebuild supervisor snapshot from current durable OpenWorker state.", {}),
        _tool("supervisor_decision", "Record an auditable decision receipt; never include chain-of-thought.", {
            "decision_id": s, "job_id": s,
            "decision_type": {"type": "string", "enum": ["submit", "retry", "cancel", "wait", "inspect", "replan", "escalate"]},
            "reason_code": s, "input_state_hash": s, "result": s,
        }, ["decision_type", "reason_code"]),
        _tool("cluster_status", "Read OpenWorker cluster status.", {}),
        _tool("cluster_agents", "Read cluster agent/worker slots.", {}),
        _tool("cluster_capabilities", "Read currently advertised node capabilities.", {}),
        _tool("job_status", "Read one durable local job.", {"job_id": s}, ["job_id"]),
        _tool("job_progress", "Read standardized durable progress for one job.", {"job_id": s}, ["job_id"]),
        _tool("job_submit", "Submit a durable local OpenWorker job and return after durable ACK.", {"job": {"type": "object", "additionalProperties": True}}, ["job"]),
        _tool("job_cancel", "Cancel one durable local job.", {"job_id": s}, ["job_id"]),
        _tool("job_retry", "Retry one eligible durable local job.", {"job_id": s}, ["job_id"]),
        _tool("queue_drain", "One-call local queue drain.", {"mode": {"type": "string", "enum": ["queued", "all"]}}),
    ]


class LocalSupervisorHost:
    def __init__(self, config: LocalSupervisorConfig, *, llm_client: Any | None = None,
                 node_client: OpenWorkerNodeClient | None = None, session_id: str | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if config.max_tool_rounds <= 0:
            raise ValueError("max_tool_rounds must be positive")
        self.config = config
        self.llm = llm_client or OpenAI(base_url=config.base_url.rstrip("/"), api_key=config.api_key)
        self.node = node_client or OpenWorkerNodeClient(base_url=config.openworker_url)
        self.session_id = session_id or uuid.uuid4().hex
        self.clock = clock
        self._last_heartbeat = 0.0
        self._bootstrapped = False

    def bootstrap(self, current_goal: str = "") -> dict[str, Any]:
        session = self.node.supervisor_session(self.config.supervisor_id, self.session_id, self.config.model, current_goal)
        recovered = self.node.supervisor_recover(self.config.supervisor_id, self.session_id)
        attention = self.node.supervisor_attention(self.config.supervisor_id)
        jobs = self.node.supervisor_jobs(self.config.supervisor_id)
        agents = self.node.cluster_agents()
        capabilities = self.node.cluster_capabilities()
        self._last_heartbeat = self.clock()
        self._bootstrapped = True
        return {"session": session, "recovered": recovered, "attention": attention, "jobs": jobs, "agents": agents, "capabilities": capabilities}

    def maybe_heartbeat(self, current_goal: str = "") -> None:
        if not self._bootstrapped:
            raise RuntimeError("bootstrap required before heartbeat")
        now = self.clock()
        if now - self._last_heartbeat >= self.config.heartbeat_interval_sec:
            self.node.supervisor_heartbeat(self.config.supervisor_id, self.session_id, current_goal)
            self._last_heartbeat = now

    def run_turn(self, user_message: str, *, current_goal: str = "") -> str:
        bootstrap = self.bootstrap(current_goal) if not self._bootstrapped else {
            "snapshot": self.node.supervisor_snapshot(self.config.supervisor_id),
            "attention": self.node.supervisor_attention(self.config.supervisor_id),
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SUPERVISOR_SYSTEM_CONTRACT},
            {"role": "system", "content": "OpenWorker bootstrap facts (informational; query tools for current authority):\n" + json.dumps(bootstrap, ensure_ascii=False, default=str)},
            {"role": "user", "content": user_message},
        ]
        tools = build_tool_specs()
        for _ in range(self.config.max_tool_rounds):
            self.maybe_heartbeat(current_goal)
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
                    result = {"ok": False, "error": str(exc), "tool": call.function.name}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
        raise RuntimeError(f"max tool rounds exceeded: {self.config.max_tool_rounds}")

    @staticmethod
    def _assistant_message_dict(message: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            out["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in message.tool_calls]
        return out

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
        sid = self.config.supervisor_id
        if name == "supervisor_snapshot": return self.node.supervisor_snapshot(sid)
        if name == "supervisor_jobs": return self.node.supervisor_jobs(sid)
        if name == "supervisor_attention": return self.node.supervisor_attention(sid)
        if name == "supervisor_recover": return self.node.supervisor_recover(sid, self.session_id)
        if name == "supervisor_decision":
            return self.node.supervisor_decision({
                "decision_id": str(args.get("decision_id") or uuid.uuid4().hex), "supervisor_id": sid, "session_id": self.session_id,
                "job_id": str(args.get("job_id", "")), "decision_type": _require(args, "decision_type"), "reason_code": _require(args, "reason_code"),
                "input_state_hash": str(args.get("input_state_hash", "")), "result": str(args.get("result", "")),
            })
        if name == "cluster_status": return self.node.cluster_status()
        if name == "cluster_agents": return self.node.cluster_agents()
        if name == "cluster_capabilities": return self.node.cluster_capabilities()
        if name == "job_status": return self.node.job_status(_require(args, "job_id"))
        if name == "job_progress": return self.node.job_progress(_require(args, "job_id"))
        if name == "job_submit":
            job = args.get("job")
            if not isinstance(job, dict): raise ToolDispatchError("job_submit requires object field 'job'")
            return self.node.submit(job)
        if name == "job_cancel": return self.node.cancel(_require(args, "job_id"))
        if name == "job_retry": return self.node.retry(_require(args, "job_id"))
        if name == "queue_drain":
            mode = str(args.get("mode", "queued"))
            if mode not in {"queued", "all"}: raise ToolDispatchError("queue_drain mode must be queued or all")
            return self.node.drain(mode)
        raise ToolDispatchError(f"unknown tool: {name}")


def _require(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if value is None or str(value).strip() == "": raise ToolDispatchError(f"missing required argument: {key}")
    return str(value)


def default_supervisor_id() -> str:
    return f"{socket.gethostname().upper()}-CODER-01"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run OpenWorker Local Supervisor against an OpenAI-compatible llama.cpp server")
    p.add_argument("--config", default=os.environ.get("OPENWORKER_LOCAL_SUPERVISOR_CONFIG", ""))
    p.add_argument("--base-url"); p.add_argument("--model"); p.add_argument("--supervisor-id"); p.add_argument("--openworker-url")
    p.add_argument("--goal", default="")
    p.add_argument("--message", default="Recover current work, inspect attention, and decide the next safe action.")
    ns = p.parse_args(argv)
    cfg = LocalSupervisorConfig.from_toml(ns.config) if ns.config else LocalSupervisorConfig()
    if ns.base_url: cfg.base_url = ns.base_url
    if ns.model: cfg.model = ns.model
    if ns.supervisor_id: cfg.supervisor_id = ns.supervisor_id
    elif cfg.supervisor_id == "LOCAL-CODER-01": cfg.supervisor_id = default_supervisor_id()
    if ns.openworker_url: cfg.openworker_url = ns.openworker_url
    print(LocalSupervisorHost(cfg).run_turn(ns.message, current_goal=ns.goal))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
