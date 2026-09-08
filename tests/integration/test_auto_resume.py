from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app
from codex_harbor.domain import QuotaWindow, TaskSpec
from codex_harbor.quota import FakeQuotaProvider, QuotaManager
from codex_harbor.recovery.auto_resume import AutoResumeManager


class ThreadReader:
    def __init__(self, root):
        self.thread = {
            "id": "original",
            "cwd": str(root),
            "turns": [{"id": "turn-1", "status": "inProgress"}],
        }

    async def thread_read(self, thread_id, *, include_turns):
        assert thread_id == "original"
        return {"thread": self.thread}


def arm(repository, git_repo):
    reader = ThreadReader(git_repo)
    manager = AutoResumeManager(repository, reader)
    spec = TaskSpec(
        title="recover",
        repository=str(git_repo),
        prompt="Continue unfinished work",
        model="model-a",
        reasoning_effort="high",
        conversation_mode="existing",
        origin_thread_id="original",
        preserve_thread_name=True,
        direct_prompt=True,
    )
    watch = manager.arm(spec, reader.thread, 95)
    return manager, reader, spec, watch


@pytest.mark.asyncio
async def test_explicit_reset_survives_acknowledgement_restart_and_handoff(
    repository, git_repo
):
    manager, reader, spec, old = arm(repository, git_repo)
    manager.cancel(old["id"])
    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    watch = manager.arm(
        spec, reader.thread, 95, trigger_mode="after_reset", resume_after=past
    )
    assert (
        manager.arm(
            spec, reader.thread, 95, trigger_mode="after_reset", resume_after=past
        )["id"]
        == watch["id"]
    )
    task_id = watch["task_id"]
    assert repository.get_task(task_id)["status"] == "WAIT_QUOTA"
    reader.thread["turns"][-1]["status"] = "completed"  # registration reply only
    manager = AutoResumeManager(repository, reader)
    exhausted = QuotaWindow("PRIMARY_5H", available=False, used_percent=100)
    await manager.tick([exhausted])
    assert manager.list()[-1]["state"] == "WAITING"
    ready = QuotaWindow("PRIMARY_5H", available=True, used_percent=0)
    await manager.tick([])
    await manager.tick([ready, QuotaWindow("WEEKLY", available=False)])
    assert manager.list()[-1]["state"] == "WAITING"
    # Even with quota available, do not hand off while the desktop turn is active.
    reader.thread["turns"][-1]["status"] = "inProgress"
    await manager.tick([ready])
    assert manager.list()[-1]["state"] == "WAITING"
    reader.thread["turns"][-1]["status"] = "completed"
    await manager.tick([ready])
    assert manager.list()[-1]["state"] == "HANDED_OFF"
    reader.thread_inspect_latest = AsyncMock(return_value={"thread": reader.thread})
    reader.thread["turns"][-1]["id"] = "another-completed-reply"
    await manager.tick([ready])
    assert repository.get_task(task_id)["status"] == "WAIT_QUOTA"
    quotas = QuotaManager(repository, FakeQuotaProvider([ready]))
    await quotas.refresh()
    assert quotas.release_quota_waiters() == 1
    task = repository.claim_next("recovery")
    assert (task["root_thread_id"], task["model"], task["reasoning_effort"]) == (
        "original",
        "model-a",
        "high",
    )
    await manager.tick([ready])
    assert len(repository.list_tasks()) == 1
    manager.cancel(watch["id"])


@pytest.mark.asyncio
async def test_explicit_reset_keeps_boundary_and_honours_cancellation(
    repository, git_repo
):
    manager, reader, spec, old = arm(repository, git_repo)
    manager.cancel(old["id"])
    future = (datetime.now(UTC) + timedelta(hours=5)).isoformat()
    watch = manager.arm(
        spec, reader.thread, 95, trigger_mode="after_reset", resume_after=future
    )
    reader.thread["turns"][-1]["status"] = "completed"
    await manager.tick([QuotaWindow("PRIMARY_5H")])
    assert repository.get_task(watch["task_id"])["status"] == "WAIT_QUOTA"
    assert manager.list()[-1]["resume_after"] == future
    manager.cancel(watch["id"])
    await manager.tick([QuotaWindow("PRIMARY_5H")])
    assert repository.get_task(watch["task_id"])["status"] == "CANCELLED"


def test_reset_api_rejects_reserve_and_requires_observed_boundary(repository, git_repo):
    reader = ThreadReader(git_repo)
    client = TestClient(
        create_app(repository, app_server_client=reader), base_url="http://127.0.0.1"
    )
    payload = {
        "thread_id": "original",
        "prompt": "continue",
        "model": "model-a",
        "reasoning_effort": "high",
        "trigger_mode": "after_reset",
    }
    assert client.post("/api/recovery-watches", json=payload).status_code == 409
    payload["resume_after"] = "2026-09-08T13:37:07"  # no timezone
    assert client.post("/api/recovery-watches", json=payload).status_code == 422
    payload["resume_after"] = "2026-09-08T13:37:07+08:00"
    payload["model"] = "gpt-reserve"
    assert client.post("/api/recovery-watches", json=payload).status_code == 409
    assert repository.list_tasks() == []
    payload["model"] = "model-a"
    result = client.post("/api/recovery-watches", json=payload)
    assert result.status_code == 201
    assert result.json()["resume_after"] == "2026-09-08T05:37:07+00:00"
    assert result.json()["state"] == "WAITING"
    payload["trigger_mode"] = "on_failure"
    payload.pop("resume_after")
    assert client.post("/api/recovery-watches", json=payload).status_code == 409


@pytest.mark.asyncio
async def test_threshold_failure_reset_and_restart_keep_original_thread(
    repository, git_repo
):
    manager, reader, spec, watch = arm(repository, git_repo)
    assert manager.arm(spec, reader.thread, 95)["id"] == watch["id"]
    await manager.tick([QuotaWindow("PRIMARY_5H", used_percent=94)])
    assert repository.list_tasks() == []
    reset = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    primary = QuotaWindow("PRIMARY_5H", used_percent=96, reset_at=reset)
    await manager.tick([primary])
    task = repository.get_task(manager.list()[0]["task_id"])
    assert task["status"] == "WAIT_QUOTA"
    assert task["root_thread_id"] == "original"
    assert task["threads"][0]["thread_id"] == "original"
    provider = FakeQuotaProvider([primary])
    quotas = QuotaManager(repository, provider)
    await quotas.refresh()
    assert quotas.release_quota_waiters() == 0  # current turn is still working
    reader.thread["turns"][-1].update(
        status="failed", error={"codexErrorInfo": "usageLimitExceeded"}
    )
    restarted = AutoResumeManager(repository, reader)
    primary.available = False
    primary.used_percent = 100
    await restarted.tick([primary])
    await quotas.refresh()
    assert quotas.release_quota_waiters() == 0
    assert restarted.list()[0]["state"] == "HANDED_OFF"
    with repository.db.connect() as conn:
        conn.execute(
            "UPDATE tasks SET resume_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), task["id"]),
        )
    primary.available = True
    primary.used_percent = 0
    await quotas.refresh()
    assert quotas.release_quota_waiters() == 1
    claimed = repository.claim_next("worker")
    assert claimed["root_thread_id"] == "original"
    assert claimed["model"] == "model-a"
    assert claimed["reasoning_effort"] == "high"


@pytest.mark.asyncio
@pytest.mark.parametrize("near_limit", [False, True])
async def test_normal_completion_disarms_without_replaying_work(
    repository, git_repo, near_limit
):
    manager, reader, _, _ = arm(repository, git_repo)
    if near_limit:
        await manager.tick([QuotaWindow("PRIMARY_5H", used_percent=96)])
    reader.thread["turns"][-1]["status"] = "completed"
    await manager.tick([QuotaWindow("PRIMARY_5H", used_percent=99)])
    assert manager.list()[0]["state"] == "COMPLETED"
    assert all(t["status"] == "CANCELLED" for t in repository.list_tasks())


@pytest.mark.asyncio
async def test_already_exhausted_creates_without_model_call_and_cancellation_is_durable(
    repository, git_repo
):
    manager, reader, _, watch = arm(repository, git_repo)
    reader.thread["turns"][-1].update(
        status="failed", error={"message": "You've hit your usage limit"}
    )
    await manager.tick([])
    task = repository.list_tasks()[0]
    assert task["status"] == "WAIT_QUOTA"
    assert task["root_thread_id"] == "original"
    manager.cancel(watch["id"])
    await manager.tick([QuotaWindow("PRIMARY_5H", used_percent=0)])
    assert repository.get_task(task["id"])["status"] == "CANCELLED"


def test_api_registers_current_thread_without_project_or_model_inference(
    repository, git_repo
):
    reader = ThreadReader(git_repo)
    client = TestClient(
        create_app(repository, app_server_client=reader), base_url="http://127.0.0.1"
    )
    payload = {
        "thread_id": "original",
        "prompt": "Continue",
        "model": "model-a",
        "reasoning_effort": "high",
    }
    one = client.post("/api/recovery-watches", json=payload)
    assert one.status_code == 201, one.text
    two = client.post("/api/recovery-watches", json=payload)
    assert one.json()["id"] == two.json()["id"]
    assert repository.list_tasks() == []
    existing = client.post(
        "/api/tasks", json={"thread_id": "original", "message": "Continue"}
    )
    assert existing.status_code == 201, existing.text
    assert existing.json()["root_thread_id"] == "original"
    assert existing.json()["conversation_mode"] == "existing"
    assert (
        client.post(
            "/api/recovery-watches", json={**payload, "threshold": 101}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/recovery-watches/{one.json()['id']}/cancel").status_code
        == 200
    )


@pytest.mark.asyncio
async def test_cancel_while_thread_read_is_in_flight_does_not_create_task(
    repository, git_repo
):
    manager, reader, _, watch = arm(repository, git_repo)

    async def read(*args, **kwargs):
        manager.cancel(watch["id"])
        return {"thread": reader.thread}

    reader.thread_read = read
    await manager.tick([QuotaWindow("PRIMARY_5H", used_percent=99)])
    assert repository.list_tasks() == []


@pytest.mark.asyncio
async def test_first_observation_after_reset_does_not_wait_another_window(
    repository, git_repo
):
    manager, reader, _, _ = arm(repository, git_repo)
    reader.thread["turns"][-1].update(
        status="failed", error={"message": "usageLimitExceeded"}
    )
    fresh = QuotaWindow(
        "PRIMARY_5H",
        used_percent=2,
        reset_at=(datetime.now(UTC) + timedelta(hours=5)).isoformat(),
    )
    await manager.tick([fresh])
    task = repository.list_tasks()[0]
    assert task["resume_at"] is None
    quota = QuotaManager(repository, FakeQuotaProvider([fresh]))
    await quota.refresh()
    assert quota.release_quota_waiters() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,success", [(False, True), (True, True), (True, False)]
)
async def test_reserve_is_opt_in_single_use_and_preserves_main_model(
    repository, git_repo, monkeypatch, enabled, success
):
    manager, reader, _, _watch = arm(repository, git_repo)
    manager.set_reserve_enabled(enabled)
    reader.thread["turns"][-1].update(
        status="failed", error={"message": "usageLimitExceeded"}
    )
    calls = []

    async def prepare(client, thread_id):
        calls.append(thread_id)
        if not success:
            raise RuntimeError("reserve unavailable")
        reader.thread["turns"].append({"id": "reserve-turn", "status": "completed"})
        return "Remaining: verify original work", "reserve-turn"

    monkeypatch.setattr(
        "codex_harbor.recovery.auto_resume.prepare_reserve_checkpoint", prepare
    )
    await manager.tick([QuotaWindow("PRIMARY_5H", available=False, used_percent=100)])
    task = repository.list_tasks()[0]
    assert task["root_thread_id"] == "original"
    assert task["model"] == "model-a" and task["reasoning_effort"] == "high"
    assert calls == (["original"] if enabled else [])
    assert ("Remaining:" in task["prompt"]) == (enabled and success)
    reader.thread_inspect_latest = lambda thread_id: reader.thread_read(
        thread_id, include_turns=True
    )
    await manager.tick([QuotaWindow("PRIMARY_5H", available=False, used_percent=100)])
    assert calls == (["original"] if enabled else [])
    assert repository.get_task(task["id"])["status"] == "WAIT_QUOTA"
    assert manager.list()[0]["reserve_status"] == (
        None if not enabled else "COMPLETED" if success else "FAILED"
    )


@pytest.mark.asyncio
async def test_precreated_task_never_spends_reserve(repository, git_repo, monkeypatch):
    manager, reader, _, _ = arm(repository, git_repo)
    manager.set_reserve_enabled(True)
    await manager.tick([QuotaWindow("PRIMARY_5H", used_percent=96)])

    async def forbidden(*args):
        pytest.fail("existing task needs no reserve inference")

    monkeypatch.setattr(
        "codex_harbor.recovery.auto_resume.prepare_reserve_checkpoint", forbidden
    )
    reader.thread["turns"][-1].update(
        status="failed", error={"message": "usageLimitExceeded"}
    )
    await manager.tick([QuotaWindow("PRIMARY_5H", available=False, used_percent=100)])
    assert len(repository.list_tasks()) == 1


def test_reserve_setting_persists_and_uses_actual_reserve_model(repository):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1")
    assert client.get("/api/recovery-settings").json()["allow_luna_reserve"] is False
    result = client.patch("/api/recovery-settings", json={"allow_luna_reserve": True})
    assert result.status_code == 200
    assert result.json() == {
        "allow_luna_reserve": True,
        "reserve_model": "gpt-reserve",
        "reserve_reasoning_effort": "xhigh",
        "max_reserve_turns_per_watch": 1,
    }
    assert AutoResumeManager(repository, None).settings()["allow_luna_reserve"] is True
