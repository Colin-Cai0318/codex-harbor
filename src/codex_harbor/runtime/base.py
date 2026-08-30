from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import EffectiveAgentConfig, RuntimeTurnResult


class AgentRuntime(ABC):
    @abstractmethod
    async def start_task(
        self, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        raise NotImplementedError

    @abstractmethod
    async def resume_task(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        raise NotImplementedError

    @abstractmethod
    async def start_turn(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        raise NotImplementedError

    @abstractmethod
    async def interrupt_task(self, thread_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def inspect_thread(self, thread_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> dict:
        raise NotImplementedError
