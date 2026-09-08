from __future__ import annotations

import pytest

from codex_harbor.domain import EffectiveAgentConfig
from codex_harbor.runtime.codex_app_server import (
    CodexAppServerRuntime,
    _thread_id,
    _turn_id,
)

CONFIG = EffectiveAgentConfig("model-a", "high", "model-a", "high")


class FakeClient:
    def __init__(self):
        self.calls = []

    async def thread_start(self, **kwargs):
        self.calls.append(("thread_start", kwargs))
        return {"thread": {"id": "thread-1"}}

    async def thread_resume(self, thread_id, **kwargs):
        self.calls.append(("thread_resume", thread_id, kwargs))
        return {}

    async def turn_start(self, thread_id, prompt, **kwargs):
        self.calls.append(("turn_start", thread_id, prompt, kwargs))
        return {"turn": {"id": "turn-1"}}

    async def wait_turn(self, thread_id, turn_id):
        self.calls.append(("wait_turn", thread_id, turn_id))
        return {"id": turn_id, "status": "completed"}

    async def request(self, method, params):
        self.calls.append((method, params))
        return {}

    async def thread_read(self, thread_id, *, include_turns):
        return {"thread": {"id": thread_id}, "include": include_turns}

    async def health_check(self):
        return {"ok": True}


def test_protocol_id_extractors_reject_malformed_responses():
    assert _thread_id({"threadId": "thread-flat"}) == "thread-flat"
    assert _turn_id({"turnId": "turn-flat"}) == "turn-flat"
    with pytest.raises(RuntimeError, match="thread id"):
        _thread_id({"thread": {}})
    with pytest.raises(RuntimeError, match="turn id"):
        _turn_id({"turn": {}})


@pytest.mark.asyncio
async def test_runtime_starts_resumes_interrupts_and_inspects_turns():
    client = FakeClient()
    runtime = CodexAppServerRuntime(client)  # type: ignore[arg-type]

    started = await runtime.start_task("C:/workspace", "first", CONFIG)
    assert started.status == "completed"
    assert runtime.active_turns == {}

    resumed = await runtime.resume_task("thread-old", "C:/workspace", "next", CONFIG)
    assert resumed.thread_id == "thread-old"
    assert (await runtime.inspect_thread("thread-old"))["include"] is True
    assert await runtime.health_check() == {"ok": True}

    runtime.active_turns["thread-old"] = "turn-live"
    await runtime.interrupt_task("thread-old")
    await runtime.interrupt_task("thread-idle")
    assert ("turn/interrupt", {"threadId": "thread-old", "turnId": "turn-live"}) in client.calls


@pytest.mark.asyncio
async def test_runtime_preserves_turn_error_and_cleans_active_turn_on_wait_failure():
    client = FakeClient()
    runtime = CodexAppServerRuntime(client)  # type: ignore[arg-type]

    async def failed_turn(_thread_id, turn_id):
        return {"id": turn_id, "status": "failed", "error": {"message": "quota"}}

    client.wait_turn = failed_turn  # type: ignore[method-assign]
    result = await runtime.start_turn("thread-1", "C:/workspace", "go", CONFIG)
    assert result.status == "failed"
    assert '"message": "quota"' in (result.error or "")
    assert runtime.active_turns == {}

    async def broken_wait(_thread_id, _turn_id):
        raise RuntimeError("stream ended")

    client.wait_turn = broken_wait  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="stream ended"):
        await runtime.start_turn("thread-1", "C:/workspace", "go", CONFIG)
    assert runtime.active_turns == {}
