import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app


def test_api_and_dashboard(repository, git_repo):
    client = TestClient(
        create_app(
            repository,
            max_workers=7,
            profiles={"deep_debug": {"reasoning_effort": "high"}},
        )
    )
    created = client.post(
        "/api/tasks",
        json={
            "title": "API task",
            "repository": str(git_repo),
            "prompt": "Do it",
            "acceptance_commands": [],
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Codex Harbor" in dashboard.text
    assert "data-theme" in dashboard.text
    assert "split('\\n')" in dashboard.text
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["title"] == "API task"
    assert task["latest_attempt"] is None
    assert task["worker"] is None
    assert client.get("/api/pool").json()["max_workers"] == 7
    assert client.get("/api/profiles").json() == [
        {"name": "deep_debug", "reasoning_effort": "high"}
    ]
    assert (
        client.patch(
            "/api/pool", json={"freeze_on_weekly_reset": False}
        ).json()["freeze_on_weekly_reset"]
        == 0
    )
    assert client.post("/api/pool/pause").json()["state"] == "PAUSED"
    assert client.post("/api/pool/resume").json()["state"] == "RUNNING"


def test_dashboard_javascript_is_valid(repository):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable")
    dashboard = TestClient(create_app(repository)).get("/").text
    script = dashboard.split("<script>", 1)[1].split("</script>", 1)[0]
    checked = subprocess.run(
        [
            node,
            "-e",
            "new Function(require('fs').readFileSync(0, 'utf8'))",
        ],
        input=script,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert checked.returncode == 0, checked.stderr
