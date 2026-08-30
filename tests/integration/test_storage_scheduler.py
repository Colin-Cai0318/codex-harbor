import asyncio
from pathlib import Path

import pytest

from codex_harbor.domain import (
    ConversationMode,
    EffectiveAgentConfig,
    ErrorType,
    PoolStatus,
    TaskSpec,
    TaskStatus,
    WorkspaceMode,
    utc_now,
)
from codex_harbor.scheduler import Scheduler
from codex_harbor.storage import Database, HarborRepository


def add(repository, git_repo: Path, title: str, **kwargs):
    return repository.create_task(
        TaskSpec(title=title, repository=str(git_repo), prompt=title, **kwargs)
    )


def test_max_workers_migration_seed_and_runtime_setting_persist(tmp_path):
    database = Database(tmp_path / "parallel" / "harbor.db")
    database.migrate(max_workers=7, now=utc_now())
    repository = HarborRepository(database)
    assert repository.get_pool()["max_workers"] == 7

    repository.set_max_workers(5)
    database.migrate(max_workers=9, now=utc_now())
    assert repository.get_pool()["max_workers"] == 5
    assert repository.list_events()[-1]["event_type"] == "POOL_MAX_WORKERS_CHANGED"


def test_project_conversation_fields_persist_in_schema_v5(repository, git_repo):
    task = repository.create_task(
        TaskSpec(
            task_id="T001",
            title="direct project conversation",
            repository=str(git_repo),
            prompt="Continue this Codex conversation exactly as written.",
            codex_project_id="project-1",
            conversation_mode=ConversationMode.NEW,
            conversation_cwd=str(git_repo),
            runtime_workspace_roots=[str(git_repo), str(git_repo.parent)],
            direct_prompt=True,
            preserve_thread_name=True,
        )
    )

    assert task["conversation_mode"] == ConversationMode.NEW
    assert task["conversation_cwd"] == str(git_repo)
    assert task["runtime_workspace_roots"] == [
        str(git_repo),
        str(git_repo.parent),
    ]
    assert task["direct_prompt"] == 1
    assert task["preserve_thread_name"] == 1
    with repository.db.connect() as connection:
        versions = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_version")
        }
    assert 5 in versions


@pytest.mark.asyncio
async def test_scheduler_observes_runtime_max_workers(
    repository, git_repo, config_values, tmp_path, monkeypatch
):
    for index in range(3):
        add(
            repository,
            git_repo,
            f"parallel-{index}",
            task_id=f"T00{index + 1}",
            workspace_mode=WorkspaceMode.ISOLATED,
        )

    class BlockingWorker:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, task):
            await asyncio.Event().wait()

    class QuotaManagerStub:
        async def refresh(self):
            return None

        def release_quota_waiters(self):
            return 0

    class RecoveryManagerStub:
        def recover_stale_workers(self):
            return []

    monkeypatch.setattr("codex_harbor.scheduler.scheduler.Worker", BlockingWorker)
    scheduler = Scheduler(
        repository,
        runtime=object(),
        model_registry=object(),
        quota_manager=QuotaManagerStub(),
        recovery_manager=RecoveryManagerStub(),
        config=config_values,
        data_dir=tmp_path,
    )
    repository.set_max_workers(1)
    await scheduler.tick()
    assert len(scheduler.running) == 1

    repository.set_max_workers(2)
    await scheduler.tick()
    assert len(scheduler.running) == 2

    repository.set_max_workers(1)
    await scheduler.tick()
    assert len(scheduler.running) == 2
    for future in scheduler.running.values():
        future.cancel()
    await asyncio.gather(*scheduler.running.values(), return_exceptions=True)


def test_persistent_crud_events_and_dependency(repository, git_repo):
    first = add(repository, git_repo, "first", task_id="T001")
    second = add(repository, git_repo, "second", task_id="T002", depends_on=["T001"])
    assert first["status"] == TaskStatus.READY
    assert second["status"] == TaskStatus.WAIT_DEP
    claimed = repository.claim_next("worker-1")
    assert claimed["id"] == "T001"
    repository.transition("T001", TaskStatus.RUNNING)
    repository.transition("T001", TaskStatus.SUCCEEDED)
    assert repository.refresh_dependencies() == 1
    assert repository.get_task("T002")["status"] == TaskStatus.READY
    assert any(
        event["event_type"] == "TASK_CREATED"
        for event in repository.list_events("T001")
    )


def test_priority_fifo_and_exclusive_group(repository, git_repo):
    add(repository, git_repo, "low", task_id="T001", priority=200)
    add(
        repository,
        git_repo,
        "high-a",
        task_id="T002",
        priority=10,
        exclusive_group="parser",
    )
    add(
        repository,
        git_repo,
        "high-b",
        task_id="T003",
        priority=10,
        exclusive_group="parser",
    )
    first = repository.claim_next("one")
    assert first["id"] == "T002"
    repository.transition(first["id"], TaskStatus.RUNNING)
    second = repository.claim_next("two")
    assert second["id"] == "T001"


def test_weekly_drain_preserves_ready_and_freezes_after_grandfathered(
    repository, git_repo
):
    add(repository, git_repo, "running", task_id="T001")
    add(repository, git_repo, "ready", task_id="T002")
    repository.claim_next("one")
    repository.transition("T001", TaskStatus.RUNNING)
    repository.begin_weekly_drain("week-2")
    assert repository.get_pool()["state"] == PoolStatus.DRAINING
    assert repository.get_task("T001")["grandfathered"] == 1
    assert repository.get_task("T002")["status"] == TaskStatus.READY
    assert repository.claim_next("two", grandfathered_only=True) is None
    repository.transition("T001", TaskStatus.SUCCEEDED)
    assert repository.freeze_if_drained()
    assert repository.get_pool()["state"] == PoolStatus.FROZEN
    assert repository.get_task("T002")["status"] == TaskStatus.READY


def test_running_agent_change_is_pending_until_next_turn(repository, git_repo):
    add(
        repository,
        git_repo,
        "agent",
        task_id="T001",
        model="model-a",
        reasoning_effort="high",
    )
    repository.claim_next("one")
    repository.transition("T001", TaskStatus.RUNNING)
    current = repository.update_agent_config("T001", model="model-b", reasoning="xhigh")
    assert current["model"] == "model-a"
    assert current["pending_model"] == "model-b"
    repository.apply_pending_agent_config("T001")
    applied = repository.get_task("T001")
    assert applied["model"] == "model-b" and applied["reasoning_effort"] == "xhigh"


def test_partial_agent_change_preserves_other_field_and_can_clear_inheritance(
    repository, git_repo
):
    add(
        repository,
        git_repo,
        "agent",
        task_id="T001",
        model="model-a",
        reasoning_effort="high",
    )
    changed = repository.update_agent_config("T001", reasoning="low")
    assert changed["model"] == "model-a" and changed["reasoning_effort"] == "low"
    repository.claim_next("one")
    repository.transition("T001", TaskStatus.RUNNING)
    pending = repository.update_agent_config("T001", model=None)
    assert pending["model"] == "model-a" and pending["pending_model_set"] == 1
    repository.apply_pending_agent_config("T001")
    assert repository.get_task("T001")["model"] is None


def test_v3_migration_repairs_historical_usage_limit_failure(tmp_path, git_repo):
    database = Database(tmp_path / "migration" / "harbor.db")
    database.migrate(now=utc_now())
    repository = HarborRepository(database)
    repository.add_repository(git_repo)
    task = add(repository, git_repo, "historical quota", task_id="T001")
    repository.claim_next("legacy-worker")
    repository.transition(task["id"], TaskStatus.RUNNING)
    attempt = repository.create_attempt(
        task["id"], EffectiveAgentConfig(None, None, "model-a", "medium")
    )
    repository.finish_attempt(
        task["id"],
        attempt,
        "FAILED",
        error_type=ErrorType.AGENT_FAILURE,
        error_message=(
            "{'message': \"You've hit your usage limit.\", "
            "'codexErrorInfo': 'usageLimitExceeded'}"
        ),
    )
    repository.record_failure(task["id"])
    repository.transition(task["id"], TaskStatus.FAILED)
    with database.connect() as connection:
        connection.execute("DELETE FROM schema_version WHERE version=3")

    database.migrate(now=utc_now())

    repaired = repository.get_task(task["id"])
    assert repaired["status"] == TaskStatus.WAIT_QUOTA
    assert repaired["failure_count"] == 0
    assert repaired["latest_attempt"]["result"] == "WAIT_QUOTA"
    assert repaired["latest_attempt"]["error_type"] == ErrorType.RATE_LIMIT_5H
    assert any(
        event["event_type"] == "TASK_QUOTA_FAILURE_REPAIRED"
        for event in repository.list_events(task["id"])
    )


def test_terminal_dependency_blocks_following_task_and_retry_reopens_chain(
    repository, git_repo
):
    first = add(repository, git_repo, "first", task_id="T001")
    second = add(
        repository,
        git_repo,
        "second",
        task_id="T002",
        depends_on=[first["id"]],
    )
    repository.claim_next("worker-first")
    repository.transition(first["id"], TaskStatus.RUNNING)
    repository.transition(first["id"], TaskStatus.FAILED)

    assert repository.refresh_dependencies() == 1
    blocked = repository.get_task(second["id"])
    assert blocked["status"] == TaskStatus.BLOCKED
    assert blocked["blocked_reason"] == "UPSTREAM_FAILED:T001"
    assert repository.claim_next("must-not-run") is None

    repository.retry_task(first["id"])
    assert repository.refresh_dependencies() == 1
    assert repository.get_task(second["id"])["status"] == TaskStatus.WAIT_DEP
    repository.claim_next("worker-retry")
    repository.transition(first["id"], TaskStatus.RUNNING)
    repository.transition(first["id"], TaskStatus.SUCCEEDED)
    assert repository.refresh_dependencies() == 1
    assert repository.get_task(second["id"])["status"] == TaskStatus.READY
