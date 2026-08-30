from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..domain import PoolStatus, TaskSpec
from ..storage import HarborRepository
from .dashboard import DASHBOARD


class TaskCreate(BaseModel):
    id: str | None = None
    title: str
    repository: str
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
) -> FastAPI:
    app = FastAPI(title="Codex Harbor", version="0.1.0")
    configured_profiles = profiles or {}

    def guard(call: Any) -> Any:
        try:
            return call()
        except KeyError as error:
            raise HTTPException(404, f"not found: {error.args[0]}") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

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
        return guard(
            lambda: repository.create_task(
                TaskSpec(
                    task_id=body.id,
                    title=body.title,
                    repository=body.repository,
                    prompt=body.prompt,
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
                )
            )
        )

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
