from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from coworker.local_supervisor import (
    LocalSupervisorConfig,
    LocalSupervisorHost,
    ToolDispatchError,
    build_tool_specs,
)


class FakeNode:
    def __init__(self):
        self.calls = []

    def _r(self, name, *args):
        self.calls.append((name, args)); return {"name": name, "args": list(args)}

    def supervisor_session(self, *a): return self._r("session", *a)
    def supervisor_recover(self, *a): return self._r("recover", *a)
    def supervisor_attention(self, *a): return self._r("attention", *a)
    def supervisor_jobs(self, *a): return self._r("jobs", *a)
    def cluster_agents(self): return self._r("agents")
    def cluster_capabilities(self): return self._r("capabilities")
    def supervisor_heartbeat(self, *a): return self._r("heartbeat", *a)
    def supervisor_snapshot(self, *a): return self._r("snapshot", *a)
    def supervisor_decision(self, p): return self._r("decision", p)
    def cluster_status(self): return self._r("cluster_status")
    def job_status(self, *a): return self._r("job_status", *a)
    def job_progress(self, *a): return self._r("job_progress", *a)
    def submit(self, *a): return self._r("submit", *a)
    def cancel(self, *a): return self._r("cancel", *a)
    def retry(self, *a): return self._r("retry", *a)
    def drain(self, *a): return self._r("drain", *a)


class FakeCompletions:
    def __init__(self, messages):
        self.outputs = list(messages)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.outputs.pop(0))])


class FakeLLM:
    def __init__(self, messages):
        self.chat = SimpleNamespace(completions=FakeCompletions(messages))


def msg(content="done", tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def test_partial_toml_uses_defaults(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[local_supervisor]\nmodel="qwen"\n', encoding="utf-8")
    cfg = LocalSupervisorConfig.from_toml(p)
    assert cfg.model == "qwen"
    assert cfg.base_url == "http://127.0.0.1:8080/v1"
    assert cfg.openworker_url == "http://127.0.0.1:8787"


def test_bootstrap_order_and_new_session_contract():
    node = FakeNode()
    host = LocalSupervisorHost(LocalSupervisorConfig(supervisor_id="ODA-CODER-01"), node_client=node, llm_client=FakeLLM([msg()]), session_id="S1")
    result = host.bootstrap("case0002")
    assert [x[0] for x in node.calls[:6]] == ["session", "recover", "attention", "jobs", "agents", "capabilities"]
    assert result["session"]["name"] == "session"
    assert node.calls[0][1][0:2] == ("ODA-CODER-01", "S1")


def test_tools_include_required_supervisor_surface():
    names = {t["function"]["name"] for t in build_tool_specs()}
    assert {"supervisor_recover", "supervisor_attention", "job_submit", "job_progress", "queue_drain"} <= names


def test_tool_call_result_is_fed_back_to_model():
    node = FakeNode()
    llm = FakeLLM([
        msg(None, [call("c1", "supervisor_attention", "{}")]),
        msg("continue safely"),
    ])
    host = LocalSupervisorHost(LocalSupervisorConfig(supervisor_id="ODA-CODER-01"), node_client=node, llm_client=llm, session_id="S1")
    out = host.run_turn("continue")
    assert out == "continue safely"
    second = llm.chat.completions.requests[1]["messages"]
    tool_msgs = [m for m in second if m["role"] == "tool"]
    assert tool_msgs[-1]["tool_call_id"] == "c1"
    assert '"ok": true' in tool_msgs[-1]["content"]


def test_malformed_tool_arguments_fail_closed_but_return_error_to_model():
    node = FakeNode()
    llm = FakeLLM([
        msg(None, [call("bad", "job_status", "{")]),
        msg("I will not assume success"),
    ])
    host = LocalSupervisorHost(LocalSupervisorConfig(), node_client=node, llm_client=llm, session_id="S1")
    assert host.run_turn("inspect") == "I will not assume success"
    second = llm.chat.completions.requests[1]["messages"]
    assert '"ok": false' in [m for m in second if m["role"] == "tool"][-1]["content"]


def test_unknown_tool_dispatch_fails_closed():
    host = LocalSupervisorHost(LocalSupervisorConfig(), node_client=FakeNode(), llm_client=FakeLLM([msg()]), session_id="S1")
    with pytest.raises(ToolDispatchError):
        host.dispatch_tool("unknown", "{}")


def test_max_tool_rounds_enforced():
    repeated = [msg(None, [call(f"c{i}", "supervisor_attention", "{}")]) for i in range(2)]
    host = LocalSupervisorHost(LocalSupervisorConfig(max_tool_rounds=2), node_client=FakeNode(), llm_client=FakeLLM(repeated), session_id="S1")
    with pytest.raises(RuntimeError, match="max tool rounds exceeded"):
        host.run_turn("loop")


def test_heartbeat_after_interval():
    now = [0.0]
    node = FakeNode()
    host = LocalSupervisorHost(LocalSupervisorConfig(heartbeat_interval_sec=5), node_client=node, llm_client=FakeLLM([msg()]), session_id="S1", clock=lambda: now[0])
    host.bootstrap("goal")
    now[0] = 6.0
    host.maybe_heartbeat("goal2")
    assert any(c[0] == "heartbeat" and c[1][-1] == "goal2" for c in node.calls)
