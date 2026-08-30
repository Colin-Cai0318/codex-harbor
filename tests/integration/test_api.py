from fastapi.testclient import TestClient

from codex_harbor.api import create_app


def test_api_and_dashboard(repository, git_repo):
    client = TestClient(create_app(repository))
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
    assert client.get("/").status_code == 200
    assert "CODEX HARBOR" in client.get("/").text
    assert client.get(f"/api/tasks/{task_id}").json()["title"] == "API task"
    assert client.post("/api/pool/pause").json()["state"] == "PAUSED"
    assert client.post("/api/pool/resume").json()["state"] == "RUNNING"
