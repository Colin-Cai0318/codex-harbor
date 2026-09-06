from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from codex_harbor.config import load_config
from codex_harbor.domain import PoolStatus, TaskSpec, TaskStatus
from codex_harbor.execution.local import LocalBackend, WSLBackend, platform_summary, select_backend
from codex_harbor.recovery import RecoveryManager
from codex_harbor.scheduler import Scheduler


class QuotaStub:
    def __init__(self, *, error: Exception | None = None):
        self.error = error

    async def refresh(self):
        if self.error:
            raise self.error

    def release_quota_waiters(self):
        return 0


class RecoveryStub:
    def recover_stale_workers(self):
        return 0


def make_scheduler(repository, config_values, tmp_path, *, quota=None, runtime=None):
    repository.set_pool(PoolStatus.PAUSED)
    return Scheduler(
        repository,
        runtime=runtime or object(),
        model_registry=object(),
        quota_manager=quota or QuotaStub(),
        recovery_manager=RecoveryStub(),
        config=config_values,
        data_dir=tmp_path,
    )


def test_recovery_requeues_stale_or_dead_workers_but_keeps_live_worker(
    repository, git_repo, monkeypatch
):
    stale = repository.create_task(
        TaskSpec(task_id="T001", title="stale", repository=str(git_repo), prompt="x")
    )
    repository.claim_next("stale-worker")
    repository.set_claim_running(stale["id"])
    repository.worker_heartbeat("stale-worker", stale["id"], "RUNNING", 111)
    with repository.db.connect() as connection:
        connection.execute(
            "UPDATE workers SET heartbeat_at=? WHERE worker_id='stale-worker'",
            ((datetime.now(UTC) - timedelta(minutes=5)).isoformat(),),
        )

    repository.worker_heartbeat("live-worker", None, "IDLE", 222)
    monkeypatch.setattr("codex_harbor.recovery.manager.psutil.pid_exists", lambda pid: pid == 222)

    assert RecoveryManager(repository, stale_seconds=45).recover_stale_workers() == 1
    assert repository.get_task(stale["id"])["status"] == TaskStatus.READY
    assert [item["worker_id"] for item in repository.list_workers()] == ["live-worker"]
    events = repository.list_events(stale["id"])
    assert any(item["event_type"] == "WORKER_DIED" for item in events)
    assert any(item["event_type"] == "TASK_RECOVERY_QUEUED" for item in events)


@pytest.mark.asyncio
async def test_scheduler_contains_worker_crash_interrupt_and_quota_provider_failures(
    repository, git_repo, config_values, tmp_path
):
    task = repository.create_task(
        TaskSpec(task_id="T001", title="faults", repository=str(git_repo), prompt="x")
    )
    repository.claim_next("worker")
    repository.set_claim_running(task["id"])

    class Runtime:
        async def interrupt_task(self, _thread_id):
            raise RuntimeError("interrupt transport closed")

    scheduler = make_scheduler(
        repository,
        config_values,
        tmp_path,
        quota=QuotaStub(error=RuntimeError("quota offline")),
        runtime=Runtime(),
    )

    async def crash():
        raise RuntimeError("worker exploded")

    crashed = asyncio.create_task(crash())
    await asyncio.sleep(0)
    scheduler.running[task["id"]] = crashed
    scheduler._reap()
    assert task["id"] not in scheduler.running
    assert repository.get_task(task["id"])["status"] == TaskStatus.BLOCKED
    assert repository.get_task(task["id"])["claimed_by"] is None

    repository.set_thread(task["id"], "thread-1", "ROOT")
    repository.cancel_task(task["id"])
    scheduler.running[task["id"]] = asyncio.create_task(asyncio.sleep(60))
    await scheduler.tick()
    scheduler.running[task["id"]].cancel()
    await asyncio.gather(scheduler.running[task["id"]], return_exceptions=True)

    event_types = [item["event_type"] for item in repository.list_events()]
    assert "WORKER_CRASHED" in event_types
    assert "TASK_INTERRUPT_FAILED" in event_types
    assert "QUOTA_REFRESH_FAILED" in event_types


@pytest.mark.asyncio
async def test_scheduler_releases_due_retry_and_stops_running_tasks(
    repository, git_repo, config_values, tmp_path
):
    task = repository.create_task(
        TaskSpec(task_id="T001", title="retry", repository=str(git_repo), prompt="x")
    )
    repository.claim_next("worker")
    repository.transition(
        task["id"], TaskStatus.RETRY_WAIT, resume_at="2000-01-01T00:00:00+00:00"
    )
    scheduler = make_scheduler(repository, config_values, tmp_path)
    assert scheduler._release_retries() == 1
    assert repository.get_task(task["id"])["status"] == TaskStatus.READY

    completed = False

    async def finish():
        nonlocal completed
        await asyncio.sleep(0)
        completed = True

    scheduler.running[task["id"]] = asyncio.create_task(finish())
    await scheduler.stop()
    assert scheduler.stopping and completed


@pytest.mark.asyncio
async def test_local_command_timeout_terminates_process_tree(tmp_path):
    backend = LocalBackend()
    command = f'"{sys.executable}" -c "import time; time.sleep(10)"'
    code, stdout, stderr = await backend.run(command, tmp_path, timeout=0.05)
    assert (code, stdout) == (124, "")
    assert "timed out after 0.05s" in stderr
    assert not backend.process_alive(999_999_999)
    backend.terminate_tree(999_999_999)


@pytest.mark.asyncio
async def test_wsl_backend_success_and_timeout_are_simulated(monkeypatch, tmp_path):
    class Process:
        pid = 12345
        returncode = 0

        def __init__(self, delay=0):
            self.delay = delay

        async def communicate(self):
            if self.delay:
                await asyncio.sleep(self.delay)
            return b"ok", b"warning"

        async def wait(self):
            return 0

    created = []

    async def create(*args, **kwargs):
        created.append((args, kwargs))
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    backend = WSLBackend()
    assert await backend.run("pwd", tmp_path, 1) == (0, "ok", "warning")
    assert created[0][0][:4] == ("wsl.exe", "--cd", str(tmp_path), "sh")

    async def create_slow(*_args, **_kwargs):
        return Process(delay=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_slow)
    monkeypatch.setattr(backend, "terminate_tree", lambda _pid: None)
    assert (await backend.run("sleep", tmp_path, 0.001))[0] == 124


def test_backend_selection_platform_summary_and_malformed_config(tmp_path, monkeypatch):
    assert select_backend("local")
    assert select_backend("wsl").__class__ is WSLBackend
    with pytest.raises(ValueError, match="unsupported"):
        select_backend("plan9")
    assert platform_summary() in {"Windows Native", "Linux Native", "WSL2"}

    config_file = tmp_path / "config.toml"
    config_file.write_text("[harbor\ninvalid", encoding="utf-8")
    with pytest.raises(Exception):
        load_config(config_file)

    data_dir = tmp_path / "custom-data"
    monkeypatch.setenv("HARBOR_DATA_DIR", str(data_dir))
    config = load_config(tmp_path / "missing.toml")
    config.ensure_layout()
    assert config.source == (tmp_path / "missing.toml").resolve()
    assert config.db_path == data_dir.resolve() / "harbor.db"
    assert (data_dir / "tasks").is_dir()
