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
        # A process can die after claiming a task and before its first heartbeat.
        # Recheck under the write lock so a late registration cannot be reclaimed.
        with self.repository.db.transaction(immediate=True) as conn:
            orphans = conn.execute(
                "SELECT id FROM tasks t WHERE status IN ('CLAIMED','RUNNING') "
                "AND updated_at < ? AND NOT EXISTS "
                "(SELECT 1 FROM workers w WHERE w.worker_id=t.claimed_by AND w.task_id=t.id)",
                (threshold.isoformat(),),
            ).fetchall()
            for task in orphans:
                conn.execute(
                    "UPDATE tasks SET status='READY',claimed_by=NULL,updated_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), task["id"]),
                )
                self.repository._event(
                    conn,
                    task["id"],
                    "TASK_RECOVERY_QUEUED",
                    {"reason": "orphaned_claim"},
                )
                recovered += 1
        return recovered
