from __future__ import annotations

import pytest

from codex_harbor.acceptance import AcceptanceRunner
from codex_harbor.codex import ModelRegistry
from codex_harbor.domain import (
    EffectiveAgentConfig,
    RuntimeTurnResult,
    TaskSpec,
    TaskStatus,
)
from codex_harbor.execution import select_backend
from codex_harbor.git import WorktreeManager
from codex_harbor.runtime import AgentRuntime
from codex_harbor.worker import Worker


class FakeRuntime(AgentRuntime):
    def __init__(self):
        self.prompts: list[str] = []

    async def start_task(
        self, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.prompts.append(prompt)
        return RuntimeTurnResult("thread-1", "turn-1", "completed")

    async def resume_task(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.prompts.append(prompt)
        return RuntimeTurnResult(thread_id, "turn-r", "completed")

    async def start_turn(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.prompts.append(prompt)
        return RuntimeTurnResult(thread_id, f"turn-{len(self.prompts)}", "completed")

    async def inspect_thread(self, thread_id: str) -> dict:
        return {"thread": {"id": thread_id}}

    async def interrupt_task(self, thread_id: str) -> None:
        return None

    async def health_check(self) -> dict:
        return {"ok": True}


MODELS = [
    {
        "model": "model-a",
        "displayName": "Model A",
        "isDefault": True,
        "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [
            {"reasoningEffort": "low", "description": ""},
            {"reasoningEffort": "medium", "description": ""},
            {"reasoningEffort": "high", "description": ""},
        ],
    }
]


@pytest.mark.asyncio
async def test_worker_persists_thread_attempt_envelope_and_succeeds(
    repository, git_repo, tmp_path, config_values
):
    task = repository.create_task(
        TaskSpec(
            title="worker",
            repository=str(git_repo),
            prompt="Implement it",
            acceptance_commands=["git status --short"],
        )
    )
    claimed = repository.claim_next("worker-test")
    runtime = FakeRuntime()
    worker = Worker(
        repository,
        runtime,
        ModelRegistry(MODELS),
        WorktreeManager(repository, tmp_path / "worktrees"),
        AcceptanceRunner(select_backend("local"), timeout=30),
        config_values,
        tmp_path / "data",
        "worker-test",
    )
    await worker.run(claimed)
    finished = repository.get_task(task["id"])
    assert finished["status"] == TaskStatus.SUCCEEDED
    assert finished["root_thread_id"] == "thread-1"
    assert (tmp_path / "data" / "tasks" / task["id"] / "recovery.json").exists()
    assert "Harbor Task ID" in runtime.prompts[0]
    with repository.db.connect() as connection:
        attempt = connection.execute(
            "SELECT thread_id FROM attempts WHERE task_id=?", (task["id"],)
        ).fetchone()
    assert attempt["thread_id"] == "thread-1"


@pytest.mark.asyncio
async def test_unsupported_model_blocks_before_execution(
    repository, git_repo, tmp_path, config_values
):
    repository.create_task(
        TaskSpec(title="bad", repository=str(git_repo), prompt="bad", model="missing")
    )
    claimed = repository.claim_next("worker-test")
    runtime = FakeRuntime()
    worker = Worker(
        repository,
        runtime,
        ModelRegistry(MODELS),
        WorktreeManager(repository, tmp_path / "worktrees"),
        AcceptanceRunner(select_backend("local")),
        config_values,
        tmp_path / "data",
        "worker-test",
    )
    await worker.run(claimed)
    assert repository.get_task(claimed["id"])["status"] == TaskStatus.BLOCKED
    assert not runtime.prompts
