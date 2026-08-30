from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from codex_harbor.acceptance import AcceptanceRunner
from codex_harbor.codex import ModelRegistry
from codex_harbor.domain import (
    EffectiveAgentConfig,
    ErrorType,
    QuotaWindow,
    RuntimeTurnResult,
    TaskSpec,
    TaskStatus,
    ThreadRole,
    SessionMode,
    WorkspaceMode,
)
from codex_harbor.execution import select_backend
from codex_harbor.git import WorktreeManager
from codex_harbor.runtime import AgentRuntime
from codex_harbor.quota.manager import QuotaManager
from codex_harbor.worker import Worker
from codex_harbor.worker.worker import classify_error


class FakeRuntime(AgentRuntime):
    def __init__(self):
        self.prompts: list[str] = []
        self.calls: list[tuple[str, str | None]] = []
        self.cwds: list[str] = []

    async def start_task(
        self, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.prompts.append(prompt)
        self.calls.append(("start", None))
        self.cwds.append(cwd)
        return RuntimeTurnResult("thread-1", "turn-1", "completed")

    async def resume_task(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.prompts.append(prompt)
        self.calls.append(("resume", thread_id))
        self.cwds.append(cwd)
        return RuntimeTurnResult(thread_id, "turn-r", "completed")

    async def start_turn(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.prompts.append(prompt)
        self.calls.append(("turn", thread_id))
        self.cwds.append(cwd)
        return RuntimeTurnResult(thread_id, f"turn-{len(self.prompts)}", "completed")

    async def inspect_thread(self, thread_id: str) -> dict:
        return {"thread": {"id": thread_id}}

    async def interrupt_task(self, thread_id: str) -> None:
        return None

    async def health_check(self) -> dict:
        return {"ok": True}


REAL_USAGE_LIMIT_ERROR = (
    "{'message': \"You've hit your usage limit. Upgrade to Pro, visit the usage "
    "page or try again at 6:10 PM.\", 'codexErrorInfo': "
    "'usageLimitExceeded', 'additionalDetails': None}"
)


class RateLimitedThenSuccessfulRuntime(FakeRuntime):
    def __init__(self):
        super().__init__()
        self.start_calls = 0
        self.resume_calls: list[str] = []

    async def start_task(
        self, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.start_calls += 1
        self.prompts.append(prompt)
        return RuntimeTurnResult(
            "thread-quota", "turn-quota", "failed", error=REAL_USAGE_LIMIT_ERROR
        )

    async def resume_task(
        self, thread_id: str, cwd: str, prompt: str, config: EffectiveAgentConfig
    ) -> RuntimeTurnResult:
        self.resume_calls.append(thread_id)
        self.prompts.append(prompt)
        return RuntimeTurnResult(thread_id, "turn-resumed", "completed")


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
async def test_project_conversation_task_injects_raw_message_into_selected_thread(
    repository, git_repo, tmp_path, config_values
):
    conversation_cwd = git_repo / "nested-codex-cwd"
    conversation_cwd.mkdir()
    task = repository.create_task(
        TaskSpec(
            title="direct message",
            repository=str(git_repo),
            prompt="Continue exactly with this user message",
            direct_prompt=True,
            preserve_thread_name=True,
            conversation_cwd=str(conversation_cwd),
            runtime_workspace_roots=[str(git_repo)],
        )
    )
    repository.set_thread(task["id"], "existing-thread", ThreadRole.ROOT)
    runtime = FakeRuntime()
    worker = Worker(
        repository,
        runtime,
        ModelRegistry(MODELS),
        WorktreeManager(repository, tmp_path / "worktrees"),
        AcceptanceRunner(select_backend("local")),
        config_values,
        tmp_path / "data",
        "direct-message-worker",
    )

    await worker.run(repository.claim_next("direct-message-worker"))

    assert repository.get_task(task["id"])["status"] == TaskStatus.SUCCEEDED
    assert runtime.calls == [("resume", "existing-thread")]
    assert runtime.cwds == [str(conversation_cwd)]
    assert runtime.prompts == ["Continue exactly with this user message"]


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


def test_real_usage_limit_error_is_quota_not_agent_failure():
    assert classify_error(REAL_USAGE_LIMIT_ERROR) == ErrorType.RATE_LIMIT_5H


@pytest.mark.asyncio
async def test_quota_turn_is_preserved_and_new_worker_resumes_same_thread(
    repository, git_repo, tmp_path, config_values
):
    task = repository.create_task(
        TaskSpec(
            title="quota recovery",
            repository=str(git_repo),
            prompt="Continue after quota reset",
            acceptance_commands=["git status --short"],
        )
    )
    reset_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    repository.save_quota(
        "codex",
        QuotaWindow(
            "PRIMARY_5H", available=False, reset_at=reset_at, source="test"
        ),
    )
    repository.save_quota(
        "codex", QuotaWindow("WEEKLY", available=True, source="test")
    )
    runtime = RateLimitedThenSuccessfulRuntime()

    first = Worker(
        repository,
        runtime,
        ModelRegistry(MODELS),
        WorktreeManager(repository, tmp_path / "worktrees"),
        AcceptanceRunner(select_backend("local"), timeout=30),
        config_values,
        tmp_path / "data",
        "worker-quota-1",
    )
    await first.run(repository.claim_next("worker-quota-1"))

    waiting = repository.get_task(task["id"])
    assert waiting["status"] == TaskStatus.WAIT_QUOTA
    assert waiting["current_attempt"] == 1
    assert waiting["failure_count"] == 0
    assert waiting["root_thread_id"] == "thread-quota"
    assert waiting["resume_at"] == reset_at
    with repository.db.connect() as connection:
        first_attempt = dict(
            connection.execute(
                "SELECT * FROM attempts WHERE task_id=? AND attempt_number=1",
                (task["id"],),
            ).fetchone()
        )
        connection.execute(
            "UPDATE tasks SET resume_at='2000-01-01T00:00:00+00:00' WHERE id=?",
            (task["id"],),
        )
    assert first_attempt["result"] == "WAIT_QUOTA"
    assert first_attempt["thread_id"] == "thread-quota"
    assert first_attempt["turn_id"] == "turn-quota"

    repository.save_quota(
        "codex", QuotaWindow("PRIMARY_5H", available=True, source="test")
    )
    assert QuotaManager(repository, object()).release_quota_waiters() == 1
    second = Worker(
        repository,
        runtime,
        ModelRegistry(MODELS),
        WorktreeManager(repository, tmp_path / "worktrees"),
        AcceptanceRunner(select_backend("local"), timeout=30),
        config_values,
        tmp_path / "data",
        "worker-quota-2",
    )
    await second.run(repository.claim_next("worker-quota-2"))

    finished = repository.get_task(task["id"])
    assert finished["status"] == TaskStatus.SUCCEEDED
    assert finished["current_attempt"] == 2
    assert finished["failure_count"] == 0
    assert runtime.start_calls == 1
    assert runtime.resume_calls == ["thread-quota"]
    with repository.db.connect() as connection:
        attempts = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM attempts WHERE task_id=? ORDER BY attempt_number",
                (task["id"],),
            )
        ]
    assert [item["turn_id"] for item in attempts] == [
        "turn-quota",
        "turn-resumed",
    ]
    assert {item["thread_id"] for item in attempts} == {"thread-quota"}


@pytest.mark.asyncio
async def test_shared_session_group_reuses_thread_and_existing_project_workspace(
    repository, git_repo, tmp_path, config_values
):
    group = repository.create_task_group(
        title="database follow-up",
        repository=git_repo,
        session_mode=SessionMode.SHARED,
        reuse_worktree=True,
        tasks=[
            TaskSpec(
                title="database schema",
                repository=str(git_repo),
                prompt="Implement the database schema",
                acceptance_commands=["git status --short"],
            ),
            TaskSpec(
                title="database follow-up",
                repository=str(git_repo),
                prompt="Improve the schema using the previous context",
                acceptance_commands=["git status --short"],
            ),
        ],
    )
    first_id, second_id = [item["id"] for item in group["tasks"]]
    assert group["tasks"][0]["workspace_mode"] == WorkspaceMode.PROJECT
    assert group["tasks"][1]["workspace_mode"] == WorkspaceMode.INHERIT
    assert group["tasks"][1]["session_parent_task_id"] == first_id
    runtime = FakeRuntime()

    async def run_claimed(worker_id: str) -> None:
        worker = Worker(
            repository,
            runtime,
            ModelRegistry(MODELS),
            WorktreeManager(repository, tmp_path / "worktrees"),
            AcceptanceRunner(select_backend("local"), timeout=30),
            config_values,
            tmp_path / "data",
            worker_id,
        )
        await worker.run(repository.claim_next(worker_id))

    await run_claimed("shared-1")
    assert repository.refresh_dependencies() == 1
    await run_claimed("shared-2")

    first = repository.get_task(first_id)
    second = repository.get_task(second_id)
    assert first["status"] == second["status"] == TaskStatus.SUCCEEDED
    assert first["root_thread_id"] == second["root_thread_id"] == "thread-1"
    assert first["worktree_path"] == second["worktree_path"] == str(git_repo)
    assert first["workspace_owned"] == second["workspace_owned"] == 0
    assert not (tmp_path / "worktrees" / first_id).exists()
    assert not (tmp_path / "worktrees" / second_id).exists()
    assert runtime.calls == [("start", None), ("resume", "thread-1")]
    assert "Continue the shared Harbor session with a new task" in runtime.prompts[1]
    assert "Previous Task:" in runtime.prompts[1]
