from __future__ import annotations

import pytest

from codex_harbor.acceptance import AcceptanceRunner
from codex_harbor.acceptance.runner import AcceptanceResult, CommandResult
from codex_harbor.codex import AppServerError, ModelRegistry
from codex_harbor.domain import EffectiveAgentConfig, RuntimeTurnResult, TaskSpec, TaskStatus, ThreadRole
from codex_harbor.execution import select_backend
from codex_harbor.git import WorktreeManager
from codex_harbor.runtime import AgentRuntime, CodexAppServerRuntime
from codex_harbor.worker import Worker


MODELS = [
    {
        "model": "model-a",
        "displayName": "Model A",
        "isDefault": True,
        "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [
            {"reasoningEffort": "medium", "description": ""}
        ],
    }
]


class ErrorRuntime(AgentRuntime):
    def __init__(self, error: str, repository=None, task_id=None):
        self.error = error
        self.repository = repository
        self.task_id = task_id

    async def start_task(self, cwd, prompt, config):
        if self.repository:
            self.repository.cancel_task(self.task_id)
            return RuntimeTurnResult("thread-cancel", "turn-cancel", "completed")
        raise RuntimeError(self.error)

    async def resume_task(self, thread_id, cwd, prompt, config):
        return await self.start_task(cwd, prompt, config)

    async def start_turn(self, thread_id, cwd, prompt, config):
        return await self.start_task(cwd, prompt, config)

    async def interrupt_task(self, thread_id):
        return None

    async def inspect_thread(self, thread_id):
        return {}

    async def health_check(self):
        return {"ok": True}


def worker_for(repository, runtime, git_repo, tmp_path, config_values, worker_id, acceptance=None):
    return Worker(
        repository,
        runtime,
        ModelRegistry(MODELS),
        WorktreeManager(repository, tmp_path / "worktrees"),
        acceptance or AcceptanceRunner(select_backend("local"), timeout=30),
        config_values,
        tmp_path / "data",
        worker_id,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "max_attempts", "expected"),
    [
        ("authentication required", 5, TaskStatus.BLOCKED),
        ("network connection reset", 5, TaskStatus.RETRY_WAIT),
        ("agent crashed", 1, TaskStatus.FAILED),
    ],
)
async def test_runtime_failures_take_the_correct_terminal_or_retry_path(
    repository, git_repo, tmp_path, config_values, message, max_attempts, expected
):
    task = repository.create_task(
        TaskSpec(
            task_id="T001",
            title="runtime fault",
            repository=str(git_repo),
            prompt="x",
            max_attempts=max_attempts,
        )
    )
    worker = worker_for(
        repository, ErrorRuntime(message), git_repo, tmp_path, config_values, "fault-worker"
    )
    await worker.run(repository.claim_next("fault-worker"))
    finished = repository.get_task(task["id"])
    assert finished["status"] == expected
    assert repository.list_workers() == []
    if expected == TaskStatus.RETRY_WAIT:
        assert finished["resume_at"] is not None
        assert finished["failure_count"] == 1


@pytest.mark.asyncio
async def test_cancellation_during_completed_turn_remains_cancelled(
    repository, git_repo, tmp_path, config_values
):
    task = repository.create_task(
        TaskSpec(task_id="T001", title="cancel", repository=str(git_repo), prompt="x")
    )
    runtime = ErrorRuntime("", repository, task["id"])
    worker = worker_for(repository, runtime, git_repo, tmp_path, config_values, "cancel-worker")
    await worker.run(repository.claim_next("cancel-worker"))
    assert repository.get_task(task["id"])["status"] == TaskStatus.CANCELLED


class AlwaysFailAcceptance:
    async def run(self, commands, cwd):
        return AcceptanceResult(
            False,
            [CommandResult("verify", 1, "", "simulated acceptance failure")],
        )


class SuccessRuntime(ErrorRuntime):
    def __init__(self):
        super().__init__("")
        self.turns = 0

    async def start_task(self, cwd, prompt, config):
        self.turns += 1
        return RuntimeTurnResult("thread-1", f"turn-{self.turns}", "completed")

    async def start_turn(self, thread_id, cwd, prompt, config):
        self.turns += 1
        return RuntimeTurnResult(thread_id, f"turn-{self.turns}", "completed")


@pytest.mark.asyncio
async def test_exhausted_acceptance_retries_fail_without_extra_turn(
    repository, git_repo, tmp_path, config_values
):
    task = repository.create_task(
        TaskSpec(
            task_id="T001",
            title="acceptance",
            repository=str(git_repo),
            prompt="x",
            acceptance_commands=["verify"],
            max_attempts=2,
        )
    )
    runtime = SuccessRuntime()
    worker = worker_for(
        repository,
        runtime,
        git_repo,
        tmp_path,
        config_values,
        "acceptance-worker",
        AlwaysFailAcceptance(),
    )
    await worker.run(repository.claim_next("acceptance-worker"))
    finished = repository.get_task(task["id"])
    assert finished["status"] == TaskStatus.FAILED
    assert finished["failure_count"] == 2
    assert runtime.turns == 2


class ForkingClient:
    def __init__(self, *, fork_fails=False):
        self.fork_fails = fork_fails
        self.started = 0

    async def find_project_for_path(self, path):
        return {"id": "project-1"}

    async def thread_update_metadata(self, thread_id, *, project_id):
        return {}

    async def thread_set_name(self, thread_id, name):
        return {}

    async def thread_resume(self, thread_id, **kwargs):
        raise AppServerError("resume failed")

    async def thread_fork(self, thread_id, **kwargs):
        if self.fork_fails:
            raise AppServerError("fork failed")
        return {"thread": {"id": "thread-fork"}}

    async def thread_start(self, **kwargs):
        self.started += 1
        return {"thread": {"id": "thread-new"}}

    async def turn_start(self, thread_id, prompt, **kwargs):
        return {"turn": {"id": f"turn-{thread_id}"}}

    async def wait_turn(self, thread_id, turn_id):
        return {"id": turn_id, "status": "completed"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fork_fails", "expected_thread", "new_starts"),
    [(False, "thread-fork", 0), (True, "thread-new", 1)],
)
async def test_resume_failure_forks_then_falls_back_to_new_thread(
    repository,
    git_repo,
    tmp_path,
    config_values,
    fork_fails,
    expected_thread,
    new_starts,
):
    task = repository.create_task(
        TaskSpec(task_id="T001", title="recover", repository=str(git_repo), prompt="x")
    )
    repository.set_thread(task["id"], "thread-old", ThreadRole.ROOT)
    client = ForkingClient(fork_fails=fork_fails)
    runtime = CodexAppServerRuntime(client)  # type: ignore[arg-type]
    worker = worker_for(repository, runtime, git_repo, tmp_path, config_values, "recovery-worker")
    await worker.run(repository.claim_next("recovery-worker"))
    finished = repository.get_task(task["id"])
    assert finished["status"] == TaskStatus.SUCCEEDED
    assert finished["threads"][-1]["thread_id"] == expected_thread
    assert client.started == new_starts


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [
    ("usageLimitExceeded", TaskStatus.WAIT_QUOTA),
    ("authentication required", TaskStatus.BLOCKED),
    ("network timeout", TaskStatus.RETRY_WAIT),
    ("error sending request for url (https://chatgpt.com/backend-api/wham/usage)", TaskStatus.RETRY_WAIT),
    ("app server stdout closed", TaskStatus.RETRY_WAIT),
])
async def test_transient_resume_error_never_forks_session(
    repository, git_repo, tmp_path, config_values, error, expected
):
    class Client(ForkingClient):
        async def thread_resume(self, thread_id, **kwargs):
            raise AppServerError(error)

        async def thread_fork(self, *args, **kwargs):
            pytest.fail("transient errors must retain the existing session")

    task = repository.create_task(TaskSpec(
        title="preserve session", repository=str(git_repo), prompt="continue"
    ))
    repository.set_thread(task["id"], "thread-old", ThreadRole.ROOT)
    client = Client()
    worker = worker_for(repository, CodexAppServerRuntime(client), git_repo,
                        tmp_path, config_values, "preserve-worker")
    await worker.run(repository.claim_next("preserve-worker"))
    finished = repository.get_task(task["id"])
    assert finished["status"] == expected
    assert finished["root_thread_id"] == "thread-old"
    assert len(finished["threads"]) == 1
    assert client.started == 0
