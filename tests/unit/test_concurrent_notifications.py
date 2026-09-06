import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from codex_harbor.codex.app_server_client import AppServerClient, AppServerError


def completed(turn):
    return {"method": "turn/completed", "params": {"threadId": "thread", "turn": {"id": turn}}}


@pytest.mark.asyncio
async def test_buffered_completion_for_another_task_is_preserved():
    client = AppServerClient(sys.executable)
    for turn in ("second", "first"):
        client._notifications.put_nowait(completed(turn))
    assert (await client.wait_turn("thread", "first", timeout=0.1))["id"] == "first"
    assert (await client.wait_turn("thread", "second", timeout=0.1))["id"] == "second"
    assert client._notifications.empty()


@pytest.mark.asyncio
async def test_back_to_back_completions_reach_concurrent_waiters_once():
    client = AppServerClient(sys.executable)
    first = asyncio.create_task(client.wait_turn("thread", "first", timeout=0.1))
    second = asyncio.create_task(client.wait_turn("thread", "second", timeout=0.1))
    await asyncio.sleep(0)
    reader = asyncio.StreamReader()
    for value in ([], None, completed("second"), completed("first")):
        reader.feed_data(json.dumps(value).encode() + b"\n")
    reader.feed_eof()
    client.process = SimpleNamespace(stdout=reader)
    await client._read_stdout()
    assert [result["id"] for result in await asyncio.gather(first, second)] == ["first", "second"]
    assert client._notifications.empty()
    assert not client._notification_predicates


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", ["eof", "close"])
async def test_disconnection_immediately_releases_waiting_turn(disconnect):
    client = AppServerClient(sys.executable)
    waiting = asyncio.create_task(client.wait_turn("thread", "unfinished"))
    await asyncio.sleep(0)
    if disconnect == "eof":
        reader = asyncio.StreamReader()
        reader.feed_eof()
        client.process = SimpleNamespace(stdout=reader)
        await client._read_stdout()
    else:
        await client.close()
    with pytest.raises(AppServerError, match="closed"):
        await asyncio.wait_for(waiting, 0.1)
    assert not client._notification_waiters


@pytest.mark.asyncio
async def test_failed_initialization_closes_client(monkeypatch):
    client = AppServerClient(sys.executable)
    closed = []

    async def fail():
        raise AppServerError("initialize failed")

    async def close():
        closed.append(True)

    monkeypatch.setattr(client, "start", fail)
    monkeypatch.setattr(client, "close", close)
    with pytest.raises(AppServerError):
        async with client:
            pytest.fail("initialization must fail")
    assert closed == [True]
