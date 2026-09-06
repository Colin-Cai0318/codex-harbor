import asyncio

import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app
from codex_harbor.domain import TaskSpec, WorkspaceMode
from codex_harbor.scheduler import Scheduler


@pytest.mark.parametrize("fields", [{"execution_backend": "typo"}, {"max_attempts": 0}])
def test_invalid_task_is_rejected_before_scheduling(repository, git_repo, fields):
    response = TestClient(create_app(repository)).post(
        "/api/tasks", json={"title": "invalid", "prompt": "test", "repository": str(git_repo), **fields}
    )
    assert response.status_code == 409
    assert repository.list_tasks() == []


@pytest.mark.asyncio
async def test_worker_identity_is_not_reused_when_earlier_slot_finishes(
    repository, git_repo, tmp_path, config_values, monkeypatch
):
    ids = []

    class Worker:
        def __init__(self, *args):
            ids.append(args[-1])

        async def run(self, task):
            await asyncio.Event().wait()

    class Quota:
        async def refresh(self):
            pass

        def release_quota_waiters(self):
            pass

    class Recovery:
        def recover_stale_workers(self):
            pass

    monkeypatch.setattr("codex_harbor.scheduler.scheduler.Worker", Worker)
    for index in range(3):
        repository.create_task(TaskSpec(
            title=str(index), repository=str(git_repo), prompt="test",
            workspace_mode=WorkspaceMode.ISOLATED,
        ))
    repository.set_max_workers(2)
    scheduler = Scheduler(repository, object(), object(), Quota(), Recovery(), config_values, tmp_path)
    try:
        await scheduler.tick()
        first = next(iter(scheduler.running.values()))
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await scheduler.tick()
        assert len(ids) == 3
        assert len(set(ids)) == 3
    finally:
        for future in scheduler.running.values():
            future.cancel()
        await scheduler.stop()
