from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from codex_harbor.codex.app_server_client import AppServerClient, AppServerError


class Reader:
    def __init__(self, *lines: bytes):
        self.lines = list(lines)

    async def readline(self) -> bytes:
        return self.lines.pop(0) if self.lines else b""


@pytest.mark.asyncio
async def test_large_json_rpc_response_survives_real_pipe_and_close(monkeypatch):
    real_spawn = asyncio.create_subprocess_exec
    server = (
        "import sys,json\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line)\n"
        " if 'id' in m:\n"
        "  print(json.dumps({'id':m['id'],'result':{'text':'x'*200000}}),flush=True)\n"
    )

    async def spawn(*args, **kwargs):
        return await real_spawn(sys.executable, "-u", "-c", server, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    client = AppServerClient(sys.executable, request_timeout=5)
    async with client:
        result = await client.request("thread/read", {"threadId": "large"})
        assert len(result["text"]) == 200000
    assert client._reader_task.done()
    assert client._stderr_task.done()
    assert client.process is None


@pytest.mark.asyncio
async def test_request_transport_failure_and_timeout_do_not_leak_pending_entries():
    client = AppServerClient(sys.executable, request_timeout=0.001)

    async def broken_write(_message):
        raise AppServerError("pipe closed")

    client._write = broken_write  # type: ignore[method-assign]
    with pytest.raises(AppServerError, match="pipe closed"):
        await client.request("thread/read")
    assert client._pending == {}

    async def swallowed_write(_message):
        return None

    client._write = swallowed_write  # type: ignore[method-assign]
    with pytest.raises(TimeoutError):
        await client.request("thread/read")
    assert client._pending == {}


@pytest.mark.asyncio
async def test_request_error_response_and_notification_timeout_are_cleaned_up():
    client = AppServerClient(sys.executable)

    async def reply_with_error(message):
        client._pending[message["id"]].set_result(
            {"id": message["id"], "error": {"code": -1, "message": "boom"}}
        )

    client._write = reply_with_error  # type: ignore[method-assign]
    with pytest.raises(AppServerError, match="boom"):
        await client.request("turn/start")

    with pytest.raises(TimeoutError):
        await client.wait_notification("turn/completed", timeout=0.001)
    assert "turn/completed" not in client._notification_waiters


@pytest.mark.asyncio
async def test_stdout_reader_handles_bad_json_responses_approvals_and_disconnect():
    client = AppServerClient(sys.executable)
    client.process = SimpleNamespace(
        stdout=Reader(
            b"not-json\n",
            b'{"id":7,"result":{"ok":true}}\n',
            b'{"id":8,"method":"permissions/request","params":{}}\n',
            b'{"method":"turn/completed","params":{"turn":{"id":"t1"}}}\n',
        )
    )
    future = asyncio.get_running_loop().create_future()
    client._pending[7] = future
    writes = []

    async def capture(message):
        writes.append(message)

    client._write = capture  # type: ignore[method-assign]
    waiter = asyncio.create_task(client.wait_notification("turn/completed"))
    await asyncio.sleep(0)
    await client._read_stdout()

    assert (await future)["result"] == {"ok": True}
    assert writes == [{"id": 8, "result": {"decision": "decline"}}]
    assert (await waiter)["params"]["turn"]["id"] == "t1"


@pytest.mark.asyncio
async def test_unknown_server_request_is_rejected_and_stderr_is_bounded():
    client = AppServerClient(sys.executable)
    writes = []

    async def capture(message):
        writes.append(message)

    client._write = capture  # type: ignore[method-assign]
    await client._handle_server_request({"id": 3, "method": "input/request"})
    assert writes[0]["error"]["code"] == -32601

    client.process = SimpleNamespace(
        stderr=Reader(*(f"line-{index}\n".encode() for index in range(510)))
    )
    await client._read_stderr()
    assert len(client.stderr_lines) <= 500
    assert client.stderr_lines[-1] == "line-509"


@pytest.mark.asyncio
async def test_write_requires_live_process():
    client = AppServerClient(sys.executable)
    with pytest.raises(AppServerError, match="not running"):
        await client.notify("initialized")
