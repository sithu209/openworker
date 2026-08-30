"""DeepSeek Harness runtime adapter over the official ACP stdio transport.

H3 deliberately implements only the ACP surface the upstream project actually
exposes today: process lifecycle, fresh sessions, text prompts, committed
assistant messages, one-shot permission fail-closed handling, and cancellation.
Durable resume/replay, rich tool events, plans/reasoning and OpenWorker approval
bridging remain later segments.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, Sequence

from ..events import Event, EventType

ACP_PROTOCOL_VERSION = 1


class HarnessRuntimeError(RuntimeError):
    """Base error for the Harness subprocess/ACP boundary."""


class HarnessCapabilityError(HarnessRuntimeError):
    """Raised when H3 is asked for an ACP capability upstream does not expose."""


PermissionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
UpdateHandler = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class HarnessProcessConfig:
    """Configuration for one Harness ACP subprocess."""

    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    startup_timeout_s: float = 20.0
    request_timeout_s: float = 300.0

    @classmethod
    def from_env(cls, *, cwd: str | os.PathLike[str] | None = None) -> "HarnessProcessConfig":
        """Build config from OPENWORKER_HARNESS_COMMAND, failing closed if absent.

        The env value may be a JSON string array (recommended on Windows) or a
        shell-like command string. OpenWorker intentionally does not guess an
        upstream installation path in H3.
        """
        raw = os.environ.get("OPENWORKER_HARNESS_COMMAND", "").strip()
        if not raw:
            raise HarnessRuntimeError(
                "OPENWORKER_HARNESS_COMMAND is required for the harness runtime"
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = shlex.split(raw, posix=os.name != "nt")
        if isinstance(parsed, str):
            command = (parsed,)
        elif isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            command = tuple(parsed)
        else:
            raise HarnessRuntimeError(
                "OPENWORKER_HARNESS_COMMAND must be a command string or JSON string array"
            )
        if not command:
            raise HarnessRuntimeError("OPENWORKER_HARNESS_COMMAND must not be empty")
        return cls(command=command, cwd=Path(cwd or os.getcwd()).resolve())


class AcpProcessClient:
    """Minimal ACP client using the upstream NDJSON JSON-RPC stdio contract."""

    def __init__(
        self,
        config: HarnessProcessConfig,
        *,
        on_update: UpdateHandler | None = None,
        on_permission: PermissionHandler | None = None,
    ) -> None:
        self.config = config
        self._on_update = on_update or (lambda _params: None)
        self._on_permission = on_permission or self._deny_permission
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self._stderr: list[str] = []
        self._closed = False

    @staticmethod
    async def _deny_permission(_params: dict[str, Any]) -> dict[str, Any]:
        # H4 will route these requests through OpenWorker PermissionEngine.
        return {"outcome": {"outcome": "cancelled"}}

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def stderr_text(self) -> str:
        return "".join(self._stderr)

    async def start(self) -> dict[str, Any]:
        if self.running:
            return await self.initialize()
        if self._closed:
            raise HarnessRuntimeError("ACP client is closed")
        env = os.environ.copy()
        env.update(self.config.env)
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.config.command,
                cwd=str(self.config.cwd),
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise HarnessRuntimeError(
                f"failed to start Harness sidecar {self.config.command!r}: {exc}"
            ) from exc
        self._reader_task = asyncio.create_task(self._read_stdout(), name="openworker-harness-acp")
        self._stderr_task = asyncio.create_task(self._read_stderr(), name="openworker-harness-stderr")
        try:
            return await asyncio.wait_for(self.initialize(), self.config.startup_timeout_s)
        except BaseException:
            await self.close()
            raise

    async def initialize(self) -> dict[str, Any]:
        result = await self.request(
            "initialize",
            {"protocolVersion": ACP_PROTOCOL_VERSION, "clientCapabilities": {}},
        )
        if not isinstance(result, dict):
            raise HarnessRuntimeError("ACP initialize returned a non-object result")
        version = result.get("protocolVersion")
        if version != ACP_PROTOCOL_VERSION:
            raise HarnessRuntimeError(
                f"unsupported ACP protocol version {version!r}; expected {ACP_PROTOCOL_VERSION}"
            )
        return result

    async def new_session(self, cwd: Path) -> str:
        result = await self.request(
            "session/new",
            {"cwd": str(cwd.resolve()), "mcpServers": [], "additionalDirectories": []},
        )
        if not isinstance(result, dict) or not isinstance(result.get("sessionId"), str):
            raise HarnessRuntimeError("ACP session/new did not return sessionId")
        return result["sessionId"]

    async def prompt(self, session_id: str, text: str) -> str:
        result = await self.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
        )
        if not isinstance(result, dict) or not isinstance(result.get("stopReason"), str):
            raise HarnessRuntimeError("ACP session/prompt did not return stopReason")
        return result["stopReason"]

    async def cancel(self, session_id: str) -> None:
        await self.notify("session/cancel", {"sessionId": session_id})

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        if not self.running or self._process is None:
            raise HarnessRuntimeError("Harness sidecar is not running")
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(future, self.config.request_timeout_s)
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        if not self.running:
            return
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _send(self, frame: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise HarnessRuntimeError("Harness sidecar stdin is unavailable")
        payload = (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            process.stdin.write(payload)
            await process.stdin.drain()

    async def _read_stdout(self) -> None:
        process = self._process
        assert process is not None and process.stdout is not None
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    frame = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self._fail_pending(HarnessRuntimeError(f"invalid ACP stdout frame: {line!r}"))
                    raise HarnessRuntimeError("Harness stdout was not pure NDJSON JSON-RPC") from exc
                await self._dispatch(frame)
        finally:
            if not self._closed:
                code = await process.wait()
                detail = self.stderr_text.strip()
                suffix = f": {detail}" if detail else ""
                self._fail_pending(HarnessRuntimeError(f"Harness sidecar exited with code {code}{suffix}"))

    async def _read_stderr(self) -> None:
        process = self._process
        assert process is not None and process.stderr is not None
        while True:
            chunk = await process.stderr.read(4096)
            if not chunk:
                return
            self._stderr.append(chunk.decode("utf-8", errors="replace"))

    async def _dispatch(self, frame: Any) -> None:
        if not isinstance(frame, dict):
            raise HarnessRuntimeError("ACP frame must be a JSON object")
        if "id" in frame and "method" not in frame:
            request_id = frame.get("id")
            future = self._pending.get(request_id) if isinstance(request_id, int) else None
            if future is None or future.done():
                return
            if "error" in frame:
                future.set_exception(HarnessRuntimeError(f"ACP request failed: {frame['error']}"))
            else:
                future.set_result(frame.get("result"))
            return
        method = frame.get("method")
        params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
        if method == "session/update":
            self._on_update(params)
            return
        if method == "session/request_permission" and "id" in frame:
            response = await self._on_permission(params)
            await self._send({"jsonrpc": "2.0", "id": frame["id"], "result": response})
            return
        # Unknown server notifications are ignored for forward compatibility;
        # unknown requests fail explicitly instead of hanging the Harness.
        if "id" in frame:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": frame["id"],
                    "error": {"code": -32601, "message": f"unsupported server request: {method}"},
                }
            )

    def _fail_pending(self, error: Exception) -> None:
        for future in tuple(self._pending.values()):
            if not future.done():
                future.set_exception(error)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is not None and process.returncode is None:
            if process.stdin is not None:
                process.stdin.close()
                try:
                    await process.stdin.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            try:
                await asyncio.wait_for(process.wait(), 5.0)
            except asyncio.TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 3.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task is not None and task is not asyncio.current_task():
                try:
                    await task
                except (asyncio.CancelledError, HarnessRuntimeError):
                    pass
        self._fail_pending(HarnessRuntimeError("ACP client closed"))


class DeepSeekHarnessRuntime:
    """H3 AgentRuntime backed by a real Harness ACP subprocess.

    The adapter intentionally exposes only the current ACP automation subset.
    OpenWorker remains native-by-default until later governance/session/tool
    bridges and A/B validation are completed.
    """

    def __init__(
        self,
        *,
        process_config: HarnessProcessConfig | None = None,
        workspace: str | os.PathLike[str] | None = None,
    ) -> None:
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.process_config = process_config or HarnessProcessConfig.from_env(cwd=self.workspace)
        self._messages: asyncio.Queue[str] = asyncio.Queue()
        self._client = AcpProcessClient(self.process_config, on_update=self._on_update)
        self._session_id: str | None = None
        self._interrupt_task: asyncio.Task[None] | None = None

    def _on_update(self, params: dict[str, Any]) -> None:
        update = params.get("update")
        if not isinstance(update, dict) or update.get("sessionUpdate") != "agent_message_chunk":
            return
        content = update.get("content")
        if isinstance(content, dict) and content.get("type") == "text":
            text = content.get("text")
            if isinstance(text, str) and text:
                self._messages.put_nowait(text)

    async def _ensure_session(self) -> str:
        if not self._client.running:
            await self._client.start()
        if self._session_id is None:
            self._session_id = await self._client.new_session(self.workspace)
        return self._session_id

    async def run(
        self,
        user_input: str | list,
        *,
        source: Optional[dict[str, Any]] = None,
        display: Optional[str] = None,
    ) -> AsyncIterator[Event]:
        if not isinstance(user_input, str):
            raise HarnessCapabilityError("H3 Harness runtime supports text prompts only")
        while not self._messages.empty():
            self._messages.get_nowait()
        session_id = await self._ensure_session()
        yield Event(EventType.TURN_START, {"runtime": "harness", "source": source, "display": display})
        try:
            stop_reason = await self._client.prompt(session_id, user_input)
            committed: list[str] = []
            while not self._messages.empty():
                committed.append(self._messages.get_nowait())
            if committed:
                yield Event(
                    EventType.ASSISTANT_MESSAGE,
                    {"content": "".join(committed), "runtime": "harness"},
                )
            if stop_reason == "cancelled":
                yield Event(EventType.INTERRUPTED, {"runtime": "harness"})
            yield Event(
                EventType.TURN_END,
                {"runtime": "harness", "stop_reason": stop_reason},
            )
        except Exception as exc:
            yield Event(EventType.ERROR, {"runtime": "harness", "error": str(exc)})
            yield Event(EventType.TURN_END, {"runtime": "harness", "stop_reason": "error"})

    async def _cancel_current(self) -> None:
        session_id = self._session_id
        if session_id is not None:
            await self._client.cancel(session_id)

    def request_interrupt(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._interrupt_task = loop.create_task(self._cancel_current())

    def retry(self) -> AsyncIterator[Event]:
        raise HarnessCapabilityError("ACP retry is not available in H3")

    def resume(self) -> AsyncIterator[Event]:
        raise HarnessCapabilityError("ACP durable resume is not available in H3")

    def queue_steering(self, text: str, source: Optional[dict[str, Any]] = None) -> None:
        raise HarnessCapabilityError("ACP steering is not available in H3")

    def switch_model(self, model: str) -> Optional[str]:
        raise HarnessCapabilityError("ACP runtime model switching is not available in H3")

    async def health(self) -> dict[str, Any]:
        """Return process/transport health without pretending H4-H7 exist."""
        return {
            "runtime": "harness",
            "process_running": self._client.running,
            "session_created": self._session_id is not None,
            "acp_protocol_version": ACP_PROTOCOL_VERSION,
            "capabilities": {
                "fresh_session": True,
                "text_prompt": True,
                "cancel": True,
                "committed_messages": True,
                "permission_bridge": False,
                "resume": False,
                "rich_events": False,
            },
        }

    async def aclose(self) -> None:
        await self._client.close()


__all__ = [
    "ACP_PROTOCOL_VERSION",
    "AcpProcessClient",
    "DeepSeekHarnessRuntime",
    "HarnessCapabilityError",
    "HarnessProcessConfig",
    "HarnessRuntimeError",
]
