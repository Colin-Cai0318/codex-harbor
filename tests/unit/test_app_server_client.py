from __future__ import annotations

import sys

import pytest

from codex_harbor.codex.app_server_client import AppServerClient


@pytest.mark.asyncio
async def test_project_matching_and_project_bound_thread_start(tmp_path):
    project_root = (tmp_path / "Project").resolve()
    project_root.mkdir()
    client = AppServerClient(sys.executable)
    requests: list[tuple[str, dict]] = []

    async def fake_request(method, params=None, **kwargs):
        requests.append((method, params or {}))
        if method == "project/list":
            return {
                "data": [
                    {
                        "id": "project-1",
                        "name": "Project",
                        "roots": [{"path": str(project_root)}],
                    }
                ],
                "nextCursor": None,
            }
        if method == "project/read":
            return {
                "project": {
                    "id": "project-1",
                    "name": "Project",
                    "roots": [{"path": str(project_root)}],
                }
            }
        if method == "thread/list":
            return {
                "data": [{"id": "thread-1", "projectId": "project-1"}],
                "nextCursor": None,
            }
        return {"thread": {"id": "thread-1"}}

    client.request = fake_request  # type: ignore[method-assign]
    project = await client.find_project_for_path(project_root)
    assert project and project["id"] == "project-1"
    assert (await client.project_read("project-1"))["name"] == "Project"
    assert (await client.thread_list(project_id="project-1"))[0]["id"] == "thread-1"
    thread_list_params = next(
        params for method, params in requests if method == "thread/list"
    )
    assert thread_list_params["projectId"] == "project-1"
    assert "appServer" in thread_list_params["sourceKinds"]

    await client.thread_start(
        cwd=str(project_root),
        project_id="project-1",
        runtime_workspace_roots=[str(project_root)],
    )
    method, params = requests[-1]
    assert method == "thread/start"
    assert params["projectId"] == "project-1"
    assert params["runtimeWorkspaceRoots"] == [str(project_root)]
    assert params["ephemeral"] is False

    await client.thread_update_metadata("thread-1", project_id="project-1")
    assert requests[-1] == (
        "thread/metadata/update",
        {"threadId": "thread-1", "projectId": "project-1"},
    )


@pytest.mark.asyncio
async def test_model_list_can_include_hidden_models():
    client = AppServerClient(sys.executable)
    requests: list[tuple[str, dict]] = []

    async def fake_request(method, params=None, **kwargs):
        requests.append((method, params or {}))
        return {
            "data": [{"model": "gpt-reserve", "hidden": True}],
            "nextCursor": None,
        }

    client.request = fake_request  # type: ignore[method-assign]
    models = await client.model_list(include_hidden=True)
    assert models[0]["model"] == "gpt-reserve"
    assert requests == [
        (
            "model/list",
            {"cursor": None, "limit": 100, "includeHidden": True},
        )
    ]
