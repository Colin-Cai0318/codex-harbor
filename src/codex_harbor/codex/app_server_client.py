from __future__ import annotations

import asyncio
import json
import shutil
from collections import defaultdict
from pathlib import Path
from types import TracebackType
from typing import Any, Self


class AppServerError(RuntimeError):
    pass


def resolve_codex_executable(configured: str | None = None) -> str:
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return str(path.resolve())
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise FileNotFoundError(f"configured Codex executable not found: {configured}")
    for candidate in ("codex.exe", "codex", "codex.cmd"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("Codex executable not found on PATH")


class AppServerClient:
    """Async newline-delimited JSON-RPC client for `codex app-server --stdio`."""

    def __init__(self, executable: str | None = None, *, request_timeout: float = 30.0):
        self.executable = resolve_codex_executable(executable)
        self.request_timeout = request_timeout
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._notification_waiters: dict[str, list[asyncio.Future[dict[str, Any]]]] = (
            defaultdict(list)
        )
        self.stderr_lines: list[str] = []

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        self.process = await asyncio.create_subprocess_exec(
            self.executable,
            "app-server",
            "--stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex-harbor",
                    "title": "Codex Harbor",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self.notify("initialized", {})

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process and process.returncode is None:
            if process.stdin:
                process.stdin.close()
                try:
                    await process.stdin.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(AppServerError("app server closed"))
        self._pending.clear()

    async def _write(self, message: dict[str, Any]) -> None:
        if (
            not self.process
            or not self.process.stdin
            or self.process.returncode is not None
        ):
            raise AppServerError("app server is not running")
        payload = (
            json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode()
            + b"\n"
        )
        self.process.stdin.write(payload)
        await self.process.stdin.drain()

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        await self._write(message)
        try:
            response = await asyncio.wait_for(future, timeout or self.request_timeout)
        finally:
            self._pending.pop(request_id, None)
        if "error" in response:
            raise AppServerError(f"{method}: {response['error']}")
        return response.get("result", {})

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        await self._write(message)

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            if request_id is not None and ("result" in message or "error" in message):
                future = self._pending.get(request_id)
                if future and not future.done():
                    future.set_result(message)
                continue
            if request_id is not None and "method" in message:
                await self._handle_server_request(message)
                continue
            await self._notifications.put(message)
            method = message.get("method")
            for future in self._notification_waiters.pop(method, []):
                if not future.done():
                    future.set_result(message)
        error = AppServerError("app server stdout closed")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            self.stderr_lines.append(line.decode(errors="replace").rstrip())
            if len(self.stderr_lines) > 500:
                del self.stderr_lines[:100]

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        # Harbor tasks are non-interactive. Approval prompts are denied and the
        # worker classifies the resulting turn as BLOCKED instead of hanging.
        method = str(message.get("method", ""))
        response: dict[str, Any]
        if "approval" in method.lower() or "permissions/request" in method.lower():
            response = {"id": message["id"], "result": {"decision": "decline"}}
        else:
            response = {
                "id": message["id"],
                "error": {
                    "code": -32601,
                    "message": f"Harbor cannot handle interactive request: {method}",
                },
            }
        await self._write(response)

    async def wait_notification(
        self,
        method: str,
        *,
        predicate: Any = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        while not self._notifications.empty():
            message = self._notifications.get_nowait()
            if message.get("method") == method and (
                predicate is None or predicate(message)
            ):
                return message
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._notification_waiters[method].append(future)
        while True:
            message = await asyncio.wait_for(future, timeout or 3600)
            if predicate is None or predicate(message):
                return message
            future = asyncio.get_running_loop().create_future()
            self._notification_waiters[method].append(future)

    async def thread_start(
        self,
        *,
        cwd: str,
        model: str | None = None,
        approval_policy: str = "never",
        sandbox: str = "workspace-write",
    ) -> dict[str, Any]:
        return await self.request(
            "thread/start",
            {
                "cwd": str(Path(cwd).resolve()),
                "model": model,
                "approvalPolicy": approval_policy,
                "sandbox": sandbox,
                "ephemeral": False,
                "threadSource": "codex-harbor",
            },
        )

    async def thread_resume(
        self, thread_id: str, *, cwd: str | None = None, model: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"threadId": thread_id, "excludeTurns": False}
        if cwd:
            params["cwd"] = str(Path(cwd).resolve())
        if model:
            params["model"] = model
        return await self.request("thread/resume", params)

    async def thread_read(
        self, thread_id: str, *, include_turns: bool = True
    ) -> dict[str, Any]:
        return await self.request(
            "thread/read", {"threadId": thread_id, "includeTurns": include_turns}
        )

    async def thread_set_name(self, thread_id: str, name: str) -> dict[str, Any]:
        return await self.request(
            "thread/name/set", {"threadId": thread_id, "name": name}
        )

    async def thread_fork(
        self, thread_id: str, *, cwd: str | None = None, model: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "excludeTurns": False,
            "threadSource": "codex-harbor",
        }
        if cwd:
            params["cwd"] = str(Path(cwd).resolve())
        if model:
            params["model"] = model
        return await self.request("thread/fork", params)

    async def turn_start(
        self,
        thread_id: str,
        prompt: str,
        *,
        model: str | None = None,
        effort: str | None = None,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if model:
            params["model"] = model
        if effort and effort != "default":
            params["effort"] = effort
        if cwd:
            params["cwd"] = str(Path(cwd).resolve())
        return await self.request("turn/start", params)

    async def wait_turn(
        self, thread_id: str, turn_id: str, *, timeout: float = 3600
    ) -> dict[str, Any]:
        notification = await self.wait_notification(
            "turn/completed",
            predicate=lambda msg: (
                msg.get("params", {}).get("threadId") == thread_id
                and msg.get("params", {}).get("turn", {}).get("id") == turn_id
            ),
            timeout=timeout,
        )
        return notification["params"]["turn"]

    async def model_list(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            result = await self.request(
                "model/list", {"cursor": cursor, "limit": 100, "includeHidden": False}
            )
            models.extend(result.get("data", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return models

    async def rate_limits(self) -> dict[str, Any]:
        return await self.request("account/rateLimits/read")

    async def health_check(self) -> dict[str, Any]:
        result = await self.request("account/read", {"refreshToken": False})
        return {"ok": True, "account": result}
