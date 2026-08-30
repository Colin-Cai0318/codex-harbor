from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psutil

from ..storage.repository import HarborRepository


class RecoveryManager:
    def __init__(self, repository: HarborRepository, *, stale_seconds: float = 45):
        self.repository = repository
        self.stale_seconds = stale_seconds

    def recover_stale_workers(self) -> int:
        threshold = datetime.now(UTC) - timedelta(seconds=self.stale_seconds)
        recovered = 0
        for worker in self.repository.list_workers():
            heartbeat = (
                datetime.fromisoformat(worker["heartbeat_at"])
                if worker.get("heartbeat_at")
                else threshold
            )
            pid_alive = bool(worker.get("pid")) and psutil.pid_exists(
                int(worker["pid"])
            )
            if heartbeat < threshold or not pid_alive:
                task_id = worker.get("task_id")
                if task_id:
                    self.repository.force_recovery_ready(task_id, "stale_worker")
                    self.repository.add_event(
                        task_id, "WORKER_DIED", {"worker_id": worker["worker_id"]}
                    )
                    recovered += 1
                self.repository.remove_worker(worker["worker_id"])
        return recovered
