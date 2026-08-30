from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app
from codex_harbor.domain import (
    ErrorType,
    PoolStatus,
    QuotaWindow,
    TaskSpec,
    TaskStatus,
    ThreadRole,
)
from codex_harbor.quota import FakeQuotaProvider, QuotaManager
from codex_harbor.scheduler import Scheduler


LUNA = "gpt-5.6-luna"


class RecoveryManagerStub:
    def recover_stale_workers(self):
        return []


class CompletingWorker:
    seen: list[dict] = []

    def __init__(self, repository, *args, **kwargs):
        self.repository = repository

    async def run(self, task):
        self.seen.append(
            {
                "id": task["id"],
                "model": task["model"],
                "root_thread_id": task.get("root_thread_id"),
            }
        )
        self.repository.transition(task["id"], TaskStatus.RUNNING)
        self.repository.transition(task["id"], TaskStatus.SUCCEEDED)
        self.repository.clear_claim(task["id"])


def scheduler_for(repository, provider, config_values, tmp_path):
    return Scheduler(
        repository,
        runtime=object(),
        model_registry=object(),
        quota_manager=QuotaManager(repository, provider),
        recovery_manager=RecoveryManagerStub(),
        config=config_values,
        data_dir=tmp_path / "scheduler-data",
    )


async def finish_running_workers(scheduler):
    if scheduler.running:
        await asyncio.gather(*scheduler.running.values())
    scheduler._reap()


@pytest.mark.asyncio
async def test_scheduler_automatically_releases_five_hour_waiter(
    repository, git_repo, config_values, tmp_path, monkeypatch
):
    CompletingWorker.seen = []
    monkeypatch.setattr(
        "codex_harbor.scheduler.scheduler.Worker", CompletingWorker
    )
    task = repository.create_task(
        TaskSpec(
            task_id="T001",
            title="Luna five-hour recovery",
            repository=str(git_repo),
            prompt="Resume after the simulated five-hour reset.",
            model=LUNA,
            reasoning_effort="low",
        )
    )
    repository.set_thread(task["id"], "thread-before-limit", ThreadRole.ROOT)
    repository.claim_next("limited-worker")
    repository.transition(task["id"], TaskStatus.RUNNING)
    repository.transition(
        task["id"],
        TaskStatus.WAIT_QUOTA,
        reason=ErrorType.RATE_LIMIT_5H,
        resume_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    )
    repository.clear_claim(task["id"])

    primary = QuotaWindow(
        "PRIMARY_5H",
        available=False,
        used_percent=100,
        remaining=0,
        reset_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        window_id="five-hour-old",
        source="simulation",
    )
    weekly = QuotaWindow(
        "WEEKLY",
        available=True,
        used_percent=20,
        remaining=80,
        window_id="weekly-current",
        source="simulation",
    )
    provider = FakeQuotaProvider([primary, weekly])
    scheduler = scheduler_for(repository, provider, config_values, tmp_path)

    await scheduler.tick()
    assert repository.get_task(task["id"])["status"] == TaskStatus.WAIT_QUOTA
    assert CompletingWorker.seen == []

    primary.available = True
    primary.used_percent = 0
    primary.remaining = 100
    primary.reset_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    primary.window_id = "five-hour-reset"
    await scheduler.tick()
    await finish_running_workers(scheduler)

    resumed = repository.get_task(task["id"])
    assert resumed["status"] == TaskStatus.SUCCEEDED
    assert resumed["root_thread_id"] == "thread-before-limit"
    assert resumed["failure_count"] == 0
    assert CompletingWorker.seen == [
        {
            "id": task["id"],
            "model": LUNA,
            "root_thread_id": "thread-before-limit",
        }
    ]
    transitions = [
        event["payload"]
        for event in repository.list_events(task["id"])
        if event["event_type"] == "TASK_STATUS_CHANGED"
    ]
    assert any(
        item.get("from") == "WAIT_QUOTA" and item.get("to") == "READY"
        for item in transitions
    )


@pytest.mark.asyncio
async def test_weekly_reset_drains_freezes_and_manual_resume_runs_ready_luna_task(
    repository, git_repo, config_values, tmp_path, monkeypatch
):
    CompletingWorker.seen = []
    monkeypatch.setattr(
        "codex_harbor.scheduler.scheduler.Worker", CompletingWorker
    )
    running = repository.create_task(
        TaskSpec(
            task_id="T001",
            title="Grandfathered Luna task",
            repository=str(git_repo),
            prompt="Finish during weekly drain.",
            model=LUNA,
            reasoning_effort="low",
        )
    )
    queued = repository.create_task(
        TaskSpec(
            task_id="T002",
            title="Queued Luna task",
            repository=str(git_repo),
            prompt="Run only after manual pool resume.",
            model=LUNA,
            reasoning_effort="low",
        )
    )
    repository.claim_next("already-running-worker")
    repository.transition(running["id"], TaskStatus.RUNNING)

    old_reset = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    repository.save_quota(
        "fake",
        QuotaWindow(
            "WEEKLY",
            available=True,
            reset_at=old_reset,
            window_id="weekly-old",
            source="simulation",
        ),
    )
    provider = FakeQuotaProvider(
        [
            QuotaWindow(
                "PRIMARY_5H",
                available=True,
                used_percent=10,
                remaining=90,
                window_id="five-hour-current",
                source="simulation",
            ),
            QuotaWindow(
                "WEEKLY",
                available=True,
                used_percent=0,
                remaining=100,
                reset_at=(datetime.now(UTC) + timedelta(days=7)).isoformat(),
                window_id="weekly-new",
                source="simulation",
            ),
        ]
    )
    scheduler = scheduler_for(repository, provider, config_values, tmp_path)

    await scheduler.tick()
    pool = repository.get_pool()
    assert pool["state"] == PoolStatus.DRAINING
    assert pool["drain_generation"] == "weekly:weekly-new"
    assert repository.get_task(running["id"])["grandfathered"] == 1
    assert repository.get_task(queued["id"])["status"] == TaskStatus.READY
    assert CompletingWorker.seen == []

    repository.transition(running["id"], TaskStatus.SUCCEEDED)
    repository.clear_claim(running["id"])
    await scheduler.tick()
    assert repository.get_pool()["state"] == PoolStatus.FROZEN
    assert repository.get_task(queued["id"])["status"] == TaskStatus.READY
    assert CompletingWorker.seen == []

    with TestClient(create_app(repository)) as client:
        response = client.post("/api/pool/resume")
    assert response.status_code == 200
    assert response.json()["state"] == PoolStatus.RUNNING
    await scheduler.tick()
    await finish_running_workers(scheduler)

    assert repository.get_pool()["state"] == PoolStatus.RUNNING
    assert repository.get_task(queued["id"])["status"] == TaskStatus.SUCCEEDED
    assert CompletingWorker.seen == [
        {"id": queued["id"], "model": LUNA, "root_thread_id": None}
    ]
    event_types = {event["event_type"] for event in repository.list_events()}
    assert {
        "WEEKLY_WINDOW_CHANGED",
        "POOL_DRAINING",
        "POOL_FROZEN",
        "POOL_RESUMED",
    } <= event_types
