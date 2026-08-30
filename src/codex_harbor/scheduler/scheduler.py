from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..acceptance import AcceptanceRunner
from ..codex import ModelRegistry
from ..domain import PoolStatus, TaskStatus
from ..execution import select_backend
from ..git import WorktreeManager
from ..quota import QuotaManager
from ..recovery import RecoveryManager
from ..runtime import AgentRuntime
from ..storage import HarborRepository
from ..worker import Worker


class Scheduler:
    def __init__(
        self,
        repository: HarborRepository,
        runtime: AgentRuntime,
        model_registry: ModelRegistry,
        quota_manager: QuotaManager,
        recovery_manager: RecoveryManager,
        config: dict[str, Any],
        data_dir: str | Path,
    ):
        self.repository = repository
        self.runtime = runtime
        self.model_registry = model_registry
        self.quota_manager = quota_manager
        self.recovery_manager = recovery_manager
        self.config = config
        self.data_dir = Path(data_dir)
        self.running: dict[str, asyncio.Task[None]] = {}
        self.interrupting: set[str] = set()
        self.stopping = False

    def _reap(self) -> None:
        for task_id, future in list(self.running.items()):
            if future.done():
                self.running.pop(task_id, None)
                self.interrupting.discard(task_id)
                if not future.cancelled() and future.exception():
                    self.repository.add_event(
                        task_id, "WORKER_CRASHED", {"error": str(future.exception())}
                    )

    async def _interrupt_cancelled(self) -> None:
        for task_id in self.running:
            if task_id in self.interrupting:
                continue
            task = self.repository.get_task(task_id)
            if task["status"] != TaskStatus.CANCELLED:
                continue
            self.interrupting.add(task_id)
            threads = task.get("threads", [])
            if threads:
                try:
                    await self.runtime.interrupt_task(threads[-1]["thread_id"])
                except Exception as error:  # noqa: BLE001 - runtime adapters are an isolation boundary
                    self.repository.add_event(
                        task_id, "TASK_INTERRUPT_FAILED", {"error": str(error)}
                    )

    def _release_retries(self) -> int:
        now = datetime.now(UTC).isoformat()
        changed = 0
        for task in self.repository.list_tasks([TaskStatus.RETRY_WAIT]):
            if not task.get("resume_at") or task["resume_at"] <= now:
                self.repository.transition(task["id"], TaskStatus.READY)
                changed += 1
        return changed

    async def tick(self) -> None:
        self._reap()
        await self._interrupt_cancelled()
        self.recovery_manager.recover_stale_workers()
        try:
            await self.quota_manager.refresh()
        except Exception as error:  # noqa: BLE001 - quota providers must not stop scheduling
            self.repository.add_event(
                None, "QUOTA_REFRESH_FAILED", {"error": str(error)}
            )
        self.quota_manager.release_quota_waiters()
        self._release_retries()
        self.repository.refresh_dependencies()
        self.repository.freeze_if_drained()
        pool = self.repository.get_pool()
        if pool["state"] not in {PoolStatus.RUNNING, PoolStatus.DRAINING}:
            return
        max_workers = int(pool["max_workers"])
        slots = max(0, max_workers - len(self.running))
        for _ in range(slots):
            worker_id = f"worker-{len(self.running) + 1}-{id(self):x}"
            task = self.repository.claim_next(
                worker_id, grandfathered_only=pool["state"] == PoolStatus.DRAINING
            )
            if not task:
                break
            backend = select_backend(task.get("execution_backend", "local"))
            worker = Worker(
                self.repository,
                self.runtime,
                self.model_registry,
                WorktreeManager(self.repository, self.data_dir / "worktrees"),
                AcceptanceRunner(backend),
                self.config,
                self.data_dir,
                worker_id,
            )
            self.running[task["id"]] = asyncio.create_task(
                worker.run(task), name=f"harbor-{task['id']}"
            )

    async def run_forever(self) -> None:
        interval = float(self.config["scheduler"]["poll_interval_seconds"])
        while not self.stopping:
            await self.tick()
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        self.stopping = True
        if self.running:
            await asyncio.gather(*self.running.values(), return_exceptions=True)
