"""Real Codex App Server persistence proof-of-concept.

The roundtrip deliberately creates two separate App Server processes. It starts
a durable thread and a turn in process A, persists the thread id, then resumes
and reads the same thread before starting a second turn in process B.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from codex_harbor.codex import AppServerClient


def thread_id(result: dict) -> str:
    thread = result.get("thread", result)
    value = thread.get("id") or thread.get("threadId")
    if not value:
        raise RuntimeError(f"missing thread id: {result}")
    return value


def turn_id(result: dict) -> str:
    turn = result.get("turn", result)
    value = turn.get("id") or turn.get("turnId")
    if not value:
        raise RuntimeError(f"missing turn id: {result}")
    return value


async def roundtrip(workspace: Path, state_path: Path, executable: str | None) -> dict:
    evidence: dict = {
        "workspace": str(workspace),
        "started_at": datetime.now(UTC).isoformat(),
        "processes": [],
    }
    async with AppServerClient(executable) as first:
        started = await first.thread_start(
            cwd=str(workspace), approval_policy="never", sandbox="read-only"
        )
        tid = thread_id(started)
        turn = await first.turn_start(
            tid,
            "Codex Harbor Phase 0 persistence PoC. Reply with exactly HARBOR_POC_START_OK. Do not use tools or modify files.",
            effort="low",
            cwd=str(workspace),
        )
        first_completed = await first.wait_turn(tid, turn_id(turn), timeout=300)
        evidence["thread_id"] = tid
        evidence["first_turn"] = {
            "id": first_completed.get("id"),
            "status": first_completed.get("status"),
        }
        evidence["processes"].append(first.process.pid if first.process else None)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    async with AppServerClient(executable) as second:
        evidence["processes"].append(second.process.pid if second.process else None)
        resumed = await second.thread_resume(tid, cwd=str(workspace))
        read = await second.thread_read(tid, include_turns=True)
        turn = await second.turn_start(
            tid,
            "This is the second process in the Codex Harbor persistence PoC. Reply with exactly HARBOR_POC_RESUME_OK. Do not use tools or modify files.",
            effort="low",
            cwd=str(workspace),
        )
        second_completed = await second.wait_turn(tid, turn_id(turn), timeout=300)
        read_thread = read.get("thread", read)
        evidence["resume_thread_id"] = thread_id(resumed)
        evidence["read_thread_id"] = thread_id(read)
        evidence["read_turn_count"] = len(read_thread.get("turns", []))
        evidence["second_turn"] = {
            "id": second_completed.get("id"),
            "status": second_completed.get("status"),
        }
        evidence["completed_at"] = datetime.now(UTC).isoformat()
        evidence["passed"] = (
            len({pid for pid in evidence["processes"] if pid is not None}) == 2
            and evidence["thread_id"]
            == evidence["resume_thread_id"]
            == evidence["read_thread_id"]
            and evidence["first_turn"]["status"] == "completed"
            and evidence["second_turn"]["status"] == "completed"
            and evidence["read_turn_count"] >= 1
        )
        state_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--state", type=Path, default=Path(".codex-harbor-poc/state.json")
    )
    parser.add_argument("--codex")
    args = parser.parse_args()
    evidence = asyncio.run(
        roundtrip(args.workspace.resolve(), args.state.resolve(), args.codex)
    )
    print(json.dumps(evidence, indent=2))
    raise SystemExit(0 if evidence["passed"] else 1)


if __name__ == "__main__":
    main()
