import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app


class FakeProjectClient:
    def __init__(self, root):
        self.root = str(root)
        self.started: list[dict] = []
        self.names: list[tuple[str, str]] = []

    async def project_list(self):
        return [
            {"id": "project-1", "name": "Project", "roots": [{"path": self.root}]}
        ]

    async def project_read(self, project_id):
        assert project_id == "project-1"
        return (await self.project_list())[0]

    async def thread_list(self, *, project_id, archived=False):
        assert project_id == "project-1"
        return [
            {
                "id": "existing-thread",
                "name": "Existing conversation",
                "preview": "Previous context",
                "cwd": self.root,
                "projectId": project_id,
                "source": "vscode",
                "status": {"type": "notLoaded"},
            }
        ]

    async def thread_read(self, thread_id, *, include_turns=True):
        assert thread_id == "existing-thread"
        return {
            "thread": {
                "id": thread_id,
                "cwd": self.root,
                "projectId": "project-1",
            }
        }

    async def thread_start(self, **kwargs):
        self.started.append(kwargs)
        return {"thread": {"id": "new-thread", "projectId": "project-1"}}

    async def thread_set_name(self, thread_id, name):
        self.names.append((thread_id, name))
        return {}


def test_api_and_dashboard(repository, git_repo):
    client = TestClient(
        create_app(
            repository,
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
    assert 'id="languageSelect"' in dashboard.text
    assert "简体中文" in dashboard.text
    assert "harbor-language" in dashboard.text
    assert "剩余 {value}%" in dashboard.text
    assert "quota?.remaining" in dashboard.text
    assert 'id="maxWorkersInput"' in dashboard.text
    assert 'id="projectSelect"' in dashboard.text
    assert 'id="threadSelect"' in dashboard.text
    assert 'id="workspaceList"' in dashboard.text
    assert 'name="message"' in dashboard.text
    assert 'id="repositorySelect"' not in dashboard.text
    assert 'id="profileSelect"' not in dashboard.text
    assert 'name="session_parent_task_id"' not in dashboard.text
    assert 'name="origin_thread_id"' not in dashboard.text
    assert "split('\\n')" in dashboard.text
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["title"] == "API task"
    assert task["latest_attempt"] is None
    assert task["worker"] is None
    assert client.get("/api/pool").json()["max_workers"] == 3
    assert client.get("/api/profiles").json() == [
        {"name": "deep_debug", "reasoning_effort": "high"}
    ]
    assert (
        client.patch(
            "/api/pool", json={"freeze_on_weekly_reset": False}
        ).json()["freeze_on_weekly_reset"]
        == 0
    )
    assert client.patch("/api/pool", json={"max_workers": 7}).json()["max_workers"] == 7
    assert client.get("/api/pool").json()["max_workers"] == 7
    assert client.patch("/api/pool", json={"max_workers": 0}).status_code == 422
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


def test_shared_task_group_api(repository, git_repo):
    client = TestClient(create_app(repository))
    response = client.post(
        "/api/task-groups",
        json={
            "title": "shared database work",
            "repository": str(git_repo),
            "session_mode": "shared",
            "workspace_mode": "project",
            "origin_thread_id": "origin-thread",
            "tasks": [
                {"title": "schema", "prompt": "Create schema", "priority": 10},
                {"title": "follow-up", "prompt": "Improve schema", "priority": 20},
            ],
        },
    )
    assert response.status_code == 201, response.text
    group = response.json()
    assert group["session_mode"] == "shared"
    assert len(group["tasks"]) == 2
    first, second = group["tasks"]
    assert second["depends_on"] == [first["id"]]
    assert second["session_parent_task_id"] == first["id"]
    assert second["workspace_mode"] == "inherit"
    assert client.get(f"/api/task-groups/{group['id']}").status_code == 200


def test_project_driven_creation_lists_and_reuses_codex_conversations(
    repository, git_repo
):
    app_client = FakeProjectClient(git_repo)
    client = TestClient(create_app(repository, app_server_client=app_client))
    message = "\n  Continue from the existing Codex context\n"

    threads = client.get("/api/codex/projects/project-1/threads")
    assert threads.status_code == 200
    assert threads.json()[0]["id"] == "existing-thread"

    created = client.post(
        "/api/tasks",
        json={
            "codex_project_id": "project-1",
            "conversation_mode": "existing",
            "thread_id": "existing-thread",
            "message": message,
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["title"] == "Continue from the existing Codex context"
    assert task["prompt"] == message
    assert task["repository"] == str(git_repo)
    assert task["root_thread_id"] == "existing-thread"
    assert task["conversation_mode"] == "existing"
    assert task["conversation_cwd"] == str(git_repo)
    assert task["direct_prompt"] == 1
    assert task["preserve_thread_name"] == 1
    assert app_client.started == []


def test_project_driven_creation_creates_codex_thread_with_workspace_roots(
    repository, git_repo, tmp_path
):
    extra = tmp_path / "extra-context"
    extra.mkdir()
    app_client = FakeProjectClient(git_repo)
    client = TestClient(
        create_app(
            repository,
            app_server_client=app_client,
            codex_settings={
                "approval_policy": "never",
                "sandbox": "workspace-write",
            },
        )
    )

    created = client.post(
        "/api/tasks",
        json={
            "codex_project_id": "project-1",
            "conversation_mode": "new",
            "message": "Create a new Codex-visible conversation",
            "workspace_roots": [str(git_repo), str(extra)],
            "primary_workspace": str(git_repo),
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["root_thread_id"] == "new-thread"
    assert task["conversation_mode"] == "new"
    assert task["runtime_workspace_roots"] == [str(git_repo), str(extra)]
    assert app_client.started[0]["project_id"] == "project-1"
    assert app_client.started[0]["cwd"] == str(git_repo)
    assert app_client.started[0]["runtime_workspace_roots"] == [
        str(git_repo),
        str(extra),
    ]
    assert app_client.names[0][0] == "new-thread"
