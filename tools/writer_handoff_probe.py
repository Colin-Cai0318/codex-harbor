"""Opt-in writer handoff probe on an idle test thread; never starts a model turn."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from codex_harbor.codex import AppServerClient
from codex_harbor.codex.app_server_client import AppServerError
from codex_harbor.domain import utc_now


async def probe(thread_id: str) -> dict:
    evidence = {"thread_id": thread_id, "started_at": utc_now(), "model_turns": 0}
    async with AppServerClient() as owner:
        before = (await owner.thread_read(thread_id))["thread"]
        turns = before.get("turns") or []
        if not turns or turns[-1].get("status") not in {
            "completed",
            "failed",
            "interrupted",
        }:
            raise RuntimeError("probe requires a persisted idle test thread")
        resumed = await owner.thread_resume(thread_id)
        assert resumed["thread"]["id"] == thread_id
        async with AppServerClient() as contender:
            evidence["foreign_unsubscribe"] = await contender.request(
                "thread/unsubscribe", {"threadId": thread_id}
            )
            try:
                await contender.thread_resume(thread_id)
            except AppServerError as error:
                if "already has an active writer" not in str(error):
                    raise
                evidence["contention_blocked"] = True
            else:
                raise RuntimeError("expected the separate writer to be rejected")
    # Both owned child processes have exited. No desktop process is terminated.
    async with AppServerClient() as successor:
        resumed = await successor.thread_resume(thread_id)
        after = (await successor.thread_read(thread_id))["thread"]
        assert resumed["thread"]["id"] == after["id"] == thread_id
        assert after.get("turns") == turns, "probe changed conversation history"
        assert after["cwd"] == before["cwd"]
        evidence.update(
            writer_released=True, history_unchanged=True, cwd_unchanged=True
        )
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thread-id", required=True, help="Idle disposable test thread"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(probe(args.thread_id))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
