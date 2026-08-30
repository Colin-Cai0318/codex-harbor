from __future__ import annotations

from typing import Any

from ..codex.app_server_client import AppServerClient
from ..domain import EffectiveAgentConfig, RuntimeTurnResult
from .base import AgentRuntime


def _thread_id(result: dict[str, Any]) -> str:
    thread = result.get("thread", result)
    value = thread.get("id") or thread.get("threadId")
    if not value:
        raise RuntimeError(f"App Server response did not contain a thread id: {result}")
    return str(value)


def _turn_id(result: dict[str, Any]) -> str:
    turn = result.get("turn", result)
    value = turn.get("id") or turn.get("turnId")
    if not value:
        raise RuntimeError(f"App Server response did not contain a turn id: {result}")
    return str(value)


class CodexAppServerRuntime(AgentRuntime):
    def __init__(
        self,
        client: AppServerClient,
        *,
        approval_policy: str = "never",
        sandbox: str = "workspace-write",
    ):
        self.client = client
        self.approval_policy = approval_policy
        self.sandbox = sandbox
        self.active_turns: dict[str, str] = {}

    async def start_task(
        self, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        started = await self.client.thread_start(
            cwd=cwd,
            model=config.effective_model,
            approval_policy=self.approval_policy,
            sandbox=self.sandbox,
        )
        thread_id = _thread_id(started)
        return await self.start_turn(thread_id, cwd, prompt, config)

    async def resume_task(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        await self.client.thread_resume(
            thread_id, cwd=cwd, model=config.effective_model
        )
        return await self.start_turn(thread_id, cwd, prompt, config)

    async def start_turn(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        result = await self.client.turn_start(
            thread_id,
            prompt,
            model=config.effective_model,
            effort=config.effective_reasoning_effort,
            cwd=cwd,
        )
        turn_id = _turn_id(result)
        self.active_turns[thread_id] = turn_id
        try:
            completed = await self.client.wait_turn(thread_id, turn_id)
        finally:
            self.active_turns.pop(thread_id, None)
        error = completed.get("error")
        return RuntimeTurnResult(
            thread_id=thread_id,
            turn_id=turn_id,
            status=str(completed.get("status", "unknown")),
            events=[completed],
            error=str(error) if error else None,
        )

    async def interrupt_task(self, thread_id: str) -> None:
        turn_id = self.active_turns.get(thread_id)
        if turn_id:
            await self.client.request(
                "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}
            )

    async def inspect_thread(self, thread_id: str) -> dict:
        return await self.client.thread_read(thread_id, include_turns=True)

    async def health_check(self) -> dict:
        return await self.client.health_check()
