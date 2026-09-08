from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app
from codex_harbor.domain import PoolStatus, TaskSpec, WorkspaceMode
from codex_harbor.recovery import RecoveryManager


def test_cross_site_form_cannot_pause_local_daemon(repository):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1:8765")
    response = client.post(
        "/api/pool/pause",
        headers={"Origin": "https://untrusted.example"},
        data={"ignored": "value"},
    )
    assert response.status_code == 403
    assert repository.get_pool()["state"] == PoolStatus.RUNNING


def test_dns_rebinding_host_is_rejected(repository):
    client = TestClient(
        create_app(repository), base_url="http://untrusted.example:8765"
    )
    assert client.get("/api/tasks").status_code == 400


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "http://127.0.0.1:9999",
        "https://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:bad",
    ],
)
def test_untrusted_origins_cannot_change_settings(repository, origin):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1:8765")
    assert (
        client.patch(
            "/api/weekly-ping", json={"enabled": True}, headers={"Origin": origin}
        ).status_code
        == 403
    )
    assert not client.get("/api/weekly-ping").json()["enabled"]


@pytest.mark.parametrize(
    "host",
    [
        "untrusted.example",
        "127.0.0.1:bad",
        "127.0.0.1@untrusted.example",
        "[::1",
        "127.0.0.1/path",
    ],
)
def test_malformed_or_nonlocal_host_is_rejected(repository, host):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1")
    assert client.get("/api/tasks", headers={"Host": host}).status_code == 400


@pytest.mark.parametrize(
    "url", ["http://localhost:8765", "http://127.0.0.1:8765", "http://[::1]:8765"]
)
async def test_same_origin_browser_and_headerless_cli_remain_usable(repository, url):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(repository)), base_url=url
    ) as client:
        assert (
            await client.post("/api/pool/pause", headers={"Origin": url})
        ).status_code == 200
        assert (await client.post("/api/pool/resume")).status_code == 200


def test_duplicate_origin_and_fetch_metadata_are_rejected(repository):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1")
    assert (
        client.post(
            "/api/pool/pause",
            headers=[("Origin", "http://127.0.0.1"), ("Origin", "http://127.0.0.1")],
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/pool/pause", headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )


def test_fresh_claim_and_cancelled_task_are_not_recovered(repository, git_repo):
    task = repository.create_task(
        TaskSpec(title="fresh", repository=str(git_repo), prompt="test")
    )
    repository.claim_next("starting")
    assert RecoveryManager(repository).recover_stale_workers() == 0
    repository.cancel_task(task["id"])
    assert RecoveryManager(repository, stale_seconds=0).recover_stale_workers() == 0
    assert repository.get_task(task["id"])["status"] == "CANCELLED"


def test_abandoned_claim_without_worker_is_recovered(repository, git_repo):
    task = repository.create_task(
        TaskSpec(title="orphan", repository=str(git_repo), prompt="test")
    )
    repository.claim_next("never-registered")
    with repository.db.connect() as conn:
        conn.execute(
            "UPDATE tasks SET updated_at=? WHERE id=?",
            ((datetime.now(UTC) - timedelta(seconds=60)).isoformat(), task["id"]),
        )
    assert RecoveryManager(repository).recover_stale_workers() == 1
    assert repository.get_task(task["id"])["status"] == "READY"


def test_database_enforces_global_capacity_and_paused_pool(repository, git_repo):
    for i in range(4):
        repository.create_task(
            TaskSpec(
                title=str(i),
                repository=str(git_repo),
                prompt="test",
                workspace_mode=WorkspaceMode.ISOLATED,
            )
        )
    repository.set_max_workers(1)
    assert repository.claim_next("daemon-one")
    assert repository.claim_next("daemon-two") is None
    repository.set_max_workers(4)
    repository.set_pool(PoolStatus.PAUSED)
    assert repository.claim_next("daemon-three") is None
