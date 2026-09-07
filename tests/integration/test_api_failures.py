from __future__ import annotations

from fastapi.testclient import TestClient

from codex_harbor.api import create_app
from codex_harbor.codex import AppServerError


class ProjectClient:
    def __init__(self, root, *, project_roots=True):
        self.root = str(root)
        self.project_roots = project_roots
        self.thread = {
            "id": "thread-1",
            "projectId": "project-1",
            "cwd": self.root,
        }

    async def project_read(self, project_id):
        if project_id == "missing":
            raise AppServerError("missing")
        return {
            "id": project_id,
            "roots": [{"path": self.root}] if self.project_roots else [],
        }

    async def project_list(self):
        return [await self.project_read("project-1")]

    async def thread_read(self, _thread_id, *, include_turns=False):
        return {"thread": self.thread}

    async def thread_list(self, *, project_id):
        if project_id == "broken":
            raise AppServerError("transport")
        return [self.thread]

    async def thread_start(self, **_kwargs):
        return {"thread": {}}


def test_project_flow_rejects_missing_server_project_message_and_conversation(
    repository, git_repo
):
    no_server = TestClient(create_app(repository))
    assert no_server.get("/api/codex/projects").json() == []
    assert (
        no_server.post(
            "/api/tasks", json={"message": "x", "codex_project_id": "p"}
        ).status_code
        == 503
    )
    assert (
        no_server.post(
            "/api/tasks", json={"repository": str(git_repo), "prompt": "   "}
        ).status_code
        == 409
    )

    app_client = ProjectClient(git_repo)
    client = TestClient(create_app(repository, app_server_client=app_client))
    assert client.post("/api/tasks", json={"message": "x"}).status_code == 409
    assert (
        client.post(
            "/api/tasks",
            json={
                "message": "x",
                "codex_project_id": "missing",
                "conversation_mode": "new",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/tasks",
            json={
                "message": "x",
                "codex_project_id": "project-1",
                "conversation_mode": "existing",
            },
        ).status_code
        == 409
    )

    app_client.thread = {"id": "thread-1", "projectId": "other", "cwd": str(git_repo)}
    assert (
        client.post(
            "/api/tasks",
            json={
                "message": "x",
                "codex_project_id": "project-1",
                "conversation_mode": "existing",
                "thread_id": "thread-1",
            },
        ).status_code
        == 409
    )
    app_client.thread = {"id": "thread-1", "projectId": "project-1"}
    response = client.post(
        "/api/tasks",
        json={
            "message": "x",
            "codex_project_id": "project-1",
            "conversation_mode": "existing",
            "thread_id": "thread-1",
        },
    )
    assert response.status_code == 409
    assert "no workspace" in response.text


def test_new_conversation_rejects_empty_missing_and_non_git_workspaces(
    repository, git_repo, tmp_path
):
    empty_client = ProjectClient(git_repo, project_roots=False)
    client = TestClient(create_app(repository, app_server_client=empty_client))
    payload = {
        "message": "x",
        "codex_project_id": "project-1",
        "conversation_mode": "new",
    }
    assert client.post("/api/tasks", json=payload).status_code == 409

    missing = tmp_path / "missing"
    response = client.post(
        "/api/tasks", json={**payload, "workspace_roots": [str(missing)]}
    )
    assert response.status_code == 409
    assert "does not exist" in response.text

    plain = tmp_path / "plain"
    plain.mkdir()
    response = client.post(
        "/api/tasks", json={**payload, "workspace_roots": [str(plain)]}
    )
    assert response.status_code == 409
    assert "must be a Git checkout" in response.text


def test_new_thread_is_deferred_until_worker_runs(repository, git_repo):
    app_client = ProjectClient(git_repo)
    client = TestClient(
        create_app(repository, app_server_client=app_client),
        raise_server_exceptions=False,
    )
    response = client.post(
        "/api/tasks",
        json={
            "message": "x",
            "codex_project_id": "project-1",
            "conversation_mode": "new",
        },
    )
    assert response.status_code == 201
    assert response.json()["root_thread_id"] is None


def test_control_endpoints_return_explicit_errors(repository, git_repo):
    client = TestClient(create_app(repository))
    assert client.get("/api/tasks/does-not-exist").status_code == 404
    assert client.post("/api/pool/launch").status_code == 404
    assert (
        client.post(
            "/api/repositories", json={"path": str(git_repo / "missing")}
        ).status_code
        == 409
    )
    assert (
        client.patch("/api/tasks/does-not-exist", json={"model": "x"}).status_code
        == 404
    )


def test_codex_thread_list_transport_error_is_502(repository, git_repo):
    app_client = ProjectClient(git_repo)
    client = TestClient(create_app(repository, app_server_client=app_client))
    response = client.get("/api/codex/projects/broken/threads")
    assert response.status_code == 502
