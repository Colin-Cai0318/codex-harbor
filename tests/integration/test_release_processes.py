"""Release checks using isolated real processes; no model or production data."""

import asyncio
import multiprocessing
import os
from datetime import UTC, datetime

from codex_harbor.domain import (
    QuotaWindow,
    RuntimeTurnResult,
    TaskSpec,
    WorkspaceMode,
    utc_now,
)
from codex_harbor.quota.weekly_ping import WeeklyPingManager
from codex_harbor.recovery import RecoveryManager
from codex_harbor.storage import Database, HarborRepository


def claim_in_child(db_path, gate, results, index):
    repo = HarborRepository(Database(db_path))
    gate.wait(timeout=30)
    task = repo.claim_next(f"child-{index}")
    results.put(task["id"] if task else None)


def ping_in_child(db_path, gate, results, index):
    repo = HarborRepository(Database(db_path))

    async def sender(control, cwd):
        with (cwd / "sends.txt").open("a", encoding="utf-8") as f:
            f.write(f"{index}\n")
        return RuntimeTurnResult(f"thread-{index}", "turn", "completed")

    manager = WeeklyPingManager(repo, sender=sender)
    gate.wait(timeout=30)
    now = datetime(2026, 9, 8, tzinfo=UTC)
    asyncio.run(
        manager.tick(
            [
                QuotaWindow("PRIMARY_5H"),
                QuotaWindow("WEEKLY", reset_at=now.isoformat()),
            ],
            now=now,
        )
    )
    results.put(True)


def crash_in_child(db_path, mode):
    repo = HarborRepository(Database(db_path))
    if mode == "claim":
        assert repo.claim_next("crashed-before-heartbeat")
        os._exit(77)
    with repo.db.transaction(immediate=True) as conn:
        conn.execute("UPDATE pool_state SET max_workers=63 WHERE id=1")
        os._exit(77)


def compete(repository, target, count=6):
    ctx = multiprocessing.get_context("spawn")
    gate = ctx.Barrier(count)
    results = ctx.Queue()
    processes = [
        ctx.Process(target=target, args=(str(repository.db.path), gate, results, i))
        for i in range(count)
    ]
    try:
        for process in processes:
            process.start()
        values = [results.get(timeout=45) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        return values
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()


def test_real_processes_share_global_capacity(repository, git_repo):
    for i in range(8):
        repository.create_task(
            TaskSpec(
                title=str(i),
                repository=str(git_repo),
                prompt="test",
                workspace_mode=WorkspaceMode.ISOLATED,
            )
        )
    repository.set_max_workers(3)
    claimed = [x for x in compete(repository, claim_in_child) if x]
    assert len(claimed) == len(set(claimed)) == 3


def test_real_processes_serialize_same_workspace(repository, git_repo):
    for i in range(8):
        repository.create_task(
            TaskSpec(
                title=str(i),
                repository=str(git_repo),
                prompt="test",
                exclusive_group="shared-workspace",
            )
        )
    repository.set_max_workers(8)
    assert len([x for x in compete(repository, claim_in_child) if x]) == 1


def test_real_processes_send_one_weekly_message(repository):
    WeeklyPingManager(repository).set_enabled(True)
    assert all(compete(repository, ping_in_child))
    assert (
        len(
            (repository.db.path.parent / "weekly-ping" / "sends.txt")
            .read_text()
            .splitlines()
        )
        == 1
    )


def test_crash_before_heartbeat_preserves_original_thread(repository, git_repo):
    task = repository.create_task(
        TaskSpec(
            title="crash",
            repository=str(git_repo),
            prompt="test",
            conversation_mode="existing",
            origin_thread_id="original-thread",
        )
    )
    process = multiprocessing.get_context("spawn").Process(
        target=crash_in_child, args=(str(repository.db.path), "claim")
    )
    process.start()
    process.join(timeout=30)
    assert process.exitcode == 77
    assert RecoveryManager(repository, stale_seconds=0).recover_stale_workers() == 1
    recovered = repository.get_task(task["id"])
    assert recovered["status"] == "READY"
    assert recovered["root_thread_id"] == "original-thread"
    assert recovered["failure_count"] == 0


def test_crash_rolls_back_sqlite_and_backup_remigrates(repository, git_repo, tmp_path):
    task = repository.create_task(
        TaskSpec(title="backup", repository=str(git_repo), prompt="test")
    )
    process = multiprocessing.get_context("spawn").Process(
        target=crash_in_child, args=(str(repository.db.path), "transaction")
    )
    process.start()
    process.join(timeout=30)
    assert process.exitcode == 77
    assert repository.get_pool()["max_workers"] == 3
    restored = Database(tmp_path / "restored.db")
    with repository.db.connect() as source, restored.connect() as dest:
        source.backup(dest)
        assert dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert dest.execute("PRAGMA foreign_key_check").fetchall() == []
    restored.migrate(now=utc_now())
    restored.migrate(now=utc_now())
    assert HarborRepository(restored).get_task(task["id"]) == repository.get_task(
        task["id"]
    )
