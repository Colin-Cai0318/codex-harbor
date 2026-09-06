from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..codex import AppServerError
from ..domain import (
    ConversationMode,
    PoolStatus,
    SessionMode,
    TaskSpec,
    ThreadRole,
    WorkspaceMode,
)
from ..storage import HarborRepository
from .dashboard import DASHBOARD


class TaskCreate(BaseModel):
    id: str | None = None
    title: str | None = None
    repository: str | None = None
    prompt: str | None = None
    message: str | None = None
    description: str = ""
    execution_backend: str = "local"
    priority: int = 100
    depends_on: list[str] = Field(default_factory=list)
    exclusive_group: str | None = None
    acceptance_commands: list[str] = Field(default_factory=list)
    max_attempts: int = 5
    model: str | None = None
    reasoning_effort: str | None = None
    profile: str | None = None
    codex_project_id: str | None = None
    origin_thread_id: str | None = None
    session_parent_task_id: str | None = None
    reuse_parent_worktree: bool = False
    workspace_mode: WorkspaceMode = WorkspaceMode.PROJECT
    conversation_mode: ConversationMode | None = None
    thread_id: str | None = None
    primary_workspace: str | None = None
    workspace_roots: list[str] = Field(default_factory=list)


class TaskGroupItem(BaseModel):
    id: str | None = None
    title: str
    prompt: str
    description: str = ""
    execution_backend: str = "local"
    priority: int = 100
    depends_on: list[str] = Field(default_factory=list)
    exclusive_group: str | None = None
    acceptance_commands: list[str] = Field(default_factory=list)
    max_attempts: int = 5
    model: str | None = None
    reasoning_effort: str | None = None
    profile: str | None = None


class TaskGroupCreate(BaseModel):
    title: str
    repository: str
    tasks: list[TaskGroupItem] = Field(min_length=1)
    session_mode: SessionMode = SessionMode.ISOLATED
    workspace_mode: WorkspaceMode = WorkspaceMode.PROJECT
    sequential: bool = True
    codex_project_id: str | None = None
    origin_thread_id: str | None = None


class TaskPatch(BaseModel):
    model: str | None = None
    reasoning_effort: str | None = None


class PoolPatch(BaseModel):
    freeze_on_weekly_reset: bool | None = None
    max_workers: int | None = Field(default=None, ge=1, le=64)


class RepositoryCreate(BaseModel):
    path: str


def create_app(
    repository: HarborRepository,
    *,
    model_registry: Any = None,
    profiles: dict[str, dict[str, Any]] | None = None,
    app_server_client: Any = None,
    codex_settings: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI(title="Codex Harbor", version="0.1.0")
    configured_profiles = profiles or {}
    configured_codex = codex_settings or {}

    def guard(call: Any) -> Any:
        try:
            return call()
        except KeyError as error:
            raise HTTPException(404, f"not found: {error.args[0]}") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    async def git_root(path: str) -> str:
        selected = Path(path).expanduser().resolve()
        if not selected.is_dir():
            raise HTTPException(409, f"workspace does not exist: {selected}")
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(selected),
            "rev-parse",
            "--show-toplevel",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode:
            detail = stderr.decode(errors="replace").strip()
            message = f"the primary workspace must be a Git checkout: {selected}"
            raise HTTPException(409, f"{message} ({detail})" if detail else message)
        return str(Path(stdout.decode().strip()).resolve())

    def task_title(message: str) -> str:
        first_line = next(
            (line.strip(" #\t") for line in message.splitlines() if line.strip()),
            "New Codex task",
        )
        return first_line[:100]

    async def project_or_404(project_id: str) -> dict[str, Any]:
        if app_server_client is None:
            raise HTTPException(503, "Codex App Server is unavailable")
        try:
            return await app_server_client.project_read(project_id)
        except AppServerError as error:
            raise HTTPException(404, f"Codex project not found: {project_id}") from error

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        return DASHBOARD

    @app.get("/api/tasks")
    async def list_tasks() -> list[dict[str, Any]]:
        return repository.list_tasks()

    @app.get("/api/repositories")
    async def list_repositories() -> list[dict[str, Any]]:
        return repository.list_repositories()

    @app.post("/api/repositories", status_code=201)
    async def add_repository(body: RepositoryCreate) -> dict[str, Any]:
        return guard(lambda: repository.add_repository(body.path))

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        return guard(lambda: repository.get_task(task_id))

    @app.post("/api/tasks", status_code=201)
    async def create_task(body: TaskCreate) -> dict[str, Any]:
        message = body.message if body.message is not None else body.prompt or ""
        if not message.strip():
            raise HTTPException(409, "task message is required")
        project_flow = body.conversation_mode is not None or body.message is not None
        selected_thread: dict[str, Any] | None = None
        runtime_roots: list[str] = []
        primary: str | None = None
        project_id = body.codex_project_id
        repository_path = body.repository
        mode = body.conversation_mode
        if project_flow:
            if not project_id:
                raise HTTPException(409, "select a Codex project")
            project = await project_or_404(project_id)
            mode = mode or (
                ConversationMode.EXISTING if body.thread_id else ConversationMode.NEW
            )
            if mode == ConversationMode.EXISTING:
                if not body.thread_id:
                    raise HTTPException(409, "select an existing Codex conversation")
                try:
                    result = await app_server_client.thread_read(
                        body.thread_id, include_turns=False
                    )
                except AppServerError as error:
                    raise HTTPException(404, "Codex conversation not found") from error
                selected_thread = result.get("thread", result)
                if selected_thread.get("projectId") != project_id:
                    raise HTTPException(
                        409, "the selected conversation is not in this Codex project"
                    )
                primary = selected_thread.get("cwd")
                if not primary:
                    raise HTTPException(409, "the selected conversation has no workspace")
                runtime_roots = [str(Path(primary).expanduser().resolve())]
            else:
                project_roots = [item["path"] for item in project.get("roots", [])]
                requested = body.workspace_roots or project_roots
                runtime_roots = list(
                    dict.fromkeys(
                        str(Path(path).expanduser().resolve()) for path in requested
                    )
                )
                if not runtime_roots:
                    raise HTTPException(
                        409, "add at least one workspace directory for the new conversation"
                    )
                for root in runtime_roots:
                    if not Path(root).is_dir():
                        raise HTTPException(409, f"workspace does not exist: {root}")
                primary = str(
                    Path(body.primary_workspace or runtime_roots[0])
                    .expanduser()
                    .resolve()
                )
                if primary not in runtime_roots:
                    runtime_roots.insert(0, primary)
            repository_path = await git_root(primary)
            repository.add_repository(repository_path)
        elif not repository_path:
            raise HTTPException(409, "repository is required for legacy task creation")

        task = guard(
            lambda: repository.create_task(
                TaskSpec(
                    task_id=body.id,
                    title=body.title or task_title(message),
                    repository=repository_path or "",
                    prompt=message,
                    description=body.description,
                    execution_backend=body.execution_backend,
                    priority=body.priority,
                    depends_on=body.depends_on,
                    exclusive_group=body.exclusive_group,
                    acceptance_commands=body.acceptance_commands,
                    max_attempts=body.max_attempts,
                    model=body.model,
                    reasoning_effort=body.reasoning_effort,
                    profile=body.profile,
                    codex_project_id=project_id,
                    origin_thread_id=body.origin_thread_id,
                    session_parent_task_id=body.session_parent_task_id,
                    reuse_parent_worktree=body.reuse_parent_worktree,
                    workspace_mode=body.workspace_mode,
                    conversation_mode=mode,
                    conversation_cwd=primary,
                    runtime_workspace_roots=runtime_roots,
                    direct_prompt=project_flow,
                    preserve_thread_name=mode == ConversationMode.EXISTING,
                )
            )
        )
        if not project_flow:
            return task
        try:
            if selected_thread is None:
                started = await app_server_client.thread_start(
                    cwd=primary or repository_path,
                    model=body.model,
                    approval_policy=configured_codex.get("approval_policy", "never"),
                    sandbox=configured_codex.get("sandbox", "workspace-write"),
                    project_id=project_id,
                    runtime_workspace_roots=runtime_roots,
                )
                selected_thread = started.get("thread", started)
            raw_thread_id = selected_thread.get("id") or selected_thread.get(
                "threadId"
            )
            if not raw_thread_id:
                raise AppServerError("Codex App Server returned a conversation without an id")
            thread_id = str(raw_thread_id)
            repository.set_thread(
                task["id"],
                thread_id,
                ThreadRole.ROOT,
                model=body.model,
                project_id=project_id,
            )
            if mode == ConversationMode.NEW:
                try:
                    await app_server_client.thread_set_name(
                        thread_id, f'[{task["id"]}] {task["title"]}'
                    )
                except AppServerError:
                    pass
        except (AppServerError, TimeoutError, OSError) as error:
            repository.delete_task(task["id"])
            raise HTTPException(502, "failed to create Codex conversation") from error
        except Exception:
            repository.delete_task(task["id"])
            raise
        return repository.get_task(task["id"])

    @app.get("/api/task-groups")
    async def list_task_groups() -> list[dict[str, Any]]:
        return repository.list_task_groups()

    @app.get("/api/task-groups/{group_id}")
    async def get_task_group(group_id: str) -> dict[str, Any]:
        return guard(lambda: repository.get_task_group(group_id))

    @app.post("/api/task-groups", status_code=201)
    async def create_task_group(body: TaskGroupCreate) -> dict[str, Any]:
        reuse_worktree = body.workspace_mode != WorkspaceMode.ISOLATED
        return guard(
            lambda: repository.create_task_group(
                title=body.title,
                repository=body.repository,
                tasks=[
                    TaskSpec(
                        task_id=item.id,
                        title=item.title,
                        repository=body.repository,
                        prompt=item.prompt,
                        description=item.description,
                        execution_backend=item.execution_backend,
                        priority=item.priority,
                        depends_on=item.depends_on,
                        exclusive_group=item.exclusive_group,
                        acceptance_commands=item.acceptance_commands,
                        max_attempts=item.max_attempts,
                        model=item.model,
                        reasoning_effort=item.reasoning_effort,
                        profile=item.profile,
                        workspace_mode=body.workspace_mode,
                    )
                    for item in body.tasks
                ],
                session_mode=body.session_mode,
                reuse_worktree=reuse_worktree,
                sequential=body.sequential,
                codex_project_id=body.codex_project_id,
                origin_thread_id=body.origin_thread_id,
            )
        )

    @app.get("/api/codex/projects")
    async def codex_projects() -> list[dict[str, Any]]:
        if app_server_client is None:
            return []
        return await app_server_client.project_list()

    @app.get("/api/codex/projects/{project_id}/threads")
    async def codex_project_threads(project_id: str) -> list[dict[str, Any]]:
        await project_or_404(project_id)
        try:
            threads = await app_server_client.thread_list(project_id=project_id)
        except AppServerError as error:
            raise HTTPException(502, "failed to load Codex conversations") from error
        return [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "preview": item.get("preview"),
                "cwd": item.get("cwd"),
                "source": item.get("source"),
                "status": item.get("status"),
                "createdAt": item.get("createdAt"),
                "updatedAt": item.get("updatedAt"),
            }
            for item in threads
        ]

    @app.patch("/api/tasks/{task_id}")
    @app.patch("/api/tasks/{task_id}/agent")
    async def patch_task(task_id: str, body: TaskPatch) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "model" in body.model_fields_set:
            updates["model"] = body.model
        if "reasoning_effort" in body.model_fields_set:
            updates["reasoning"] = body.reasoning_effort
        return guard(lambda: repository.update_agent_config(task_id, **updates))

    @app.delete("/api/tasks/{task_id}", status_code=204)
    async def delete_task(task_id: str) -> None:
        guard(lambda: repository.delete_task(task_id))

    @app.post("/api/tasks/{task_id}/retry")
    async def retry_task(task_id: str) -> dict[str, Any]:
        return guard(lambda: repository.retry_task(task_id))

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, Any]:
        return guard(lambda: repository.cancel_task(task_id))

    @app.get("/api/pool")
    async def get_pool() -> dict[str, Any]:
        return repository.get_pool()

    @app.patch("/api/pool")
    async def patch_pool(body: PoolPatch) -> dict[str, Any]:
        if body.freeze_on_weekly_reset is not None:
            repository.set_freeze_on_weekly_reset(body.freeze_on_weekly_reset)
        if body.max_workers is not None:
            repository.set_max_workers(body.max_workers)
        return repository.get_pool()

    @app.post("/api/pool/{action}")
    async def pool_action(action: str) -> dict[str, Any]:
        states = {
            "pause": PoolStatus.PAUSED,
            "freeze": PoolStatus.FROZEN,
            "resume": PoolStatus.RUNNING,
        }
        if action not in states:
            raise HTTPException(404, "unknown pool action")
        repository.set_pool(states[action], event_type=f"POOL_{action.upper()}D")
        return repository.get_pool()

    @app.get("/api/quota")
    async def quota() -> list[dict[str, Any]]:
        return repository.list_quotas()

    @app.get("/api/models")
    async def models() -> list[dict[str, Any]]:
        if model_registry is None:
            return []
        return [
            {
                "model": item.model,
                "display_name": item.display_name,
                "is_default": item.is_default,
                "reasoning_efforts": sorted(item.reasoning_efforts),
            }
            for item in model_registry.models.values()
        ]

    @app.get("/api/profiles")
    async def profiles() -> list[dict[str, Any]]:
        return [
            {"name": name, **values}
            for name, values in sorted(configured_profiles.items())
        ]

    @app.get("/api/workers")
    async def workers() -> list[dict[str, Any]]:
        return repository.list_workers()

    @app.get("/api/events")
    async def events(
        task_id: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        return repository.list_events(task_id, min(max(limit, 1), 1000))

    return app
