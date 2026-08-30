from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..acceptance import AcceptanceRunner
from ..codex import AppServerError, ModelRegistry, ModelValidationError
from ..domain import (
    EffectiveAgentConfig,
    ErrorType,
    RuntimeTurnResult,
    TaskStatus,
    ThreadRole,
    WorkspaceMode,
)
from ..git import GitError, WorktreeManager
from ..recovery import RecoveryEnvelope, build_recovery_prompt
from ..runtime import AgentRuntime, CodexAppServerRuntime
from ..storage import HarborRepository


def classify_error(message: str) -> ErrorType:
    lowered = message.lower()
    if any(
        token in lowered
        for token in ("weekly limit", "weekly quota", "secondary rate limit")
    ):
        return ErrorType.RATE_LIMIT_WEEKLY
    if any(
        token in lowered
        for token in (
            "usagelimitexceeded",
            "hit your usage limit",
            "5 hour",
            "5-hour",
            "5h usage",
            "primary rate limit",
        )
    ):
        return ErrorType.RATE_LIMIT_5H
    if any(
        token in lowered
        for token in (
            "unauthorized",
            "authentication",
            "auth required",
            "login required",
        )
    ):
        return ErrorType.AUTH
    if "mcp" in lowered:
        return ErrorType.MCP
    if any(
        token in lowered
        for token in ("network", "connection reset", "timed out", "timeout")
    ):
        return ErrorType.NETWORK
    if "git" in lowered or "worktree" in lowered:
        return ErrorType.GIT
    if "app server" in lowered or "json-rpc" in lowered:
        return ErrorType.APP_SERVER
    return ErrorType.AGENT_FAILURE


def initial_prompt(task: dict[str, Any]) -> str:
    acceptance = (
        "\n".join(f"- {command}" for command in task["acceptance_commands"])
        or "- No acceptance commands configured"
    )
    constraints = (
        "Work only inside the assigned Git worktree. Preserve unrelated user changes. "
        "Do not expose secrets. When complete, summarize changes and tests."
    )
    return f"""Harbor Task ID: {task["id"]}
Task Title: {task["title"]}
Objective:
{task["prompt"]}

Description:
{task.get("description") or "(none)"}

Acceptance Criteria:
{acceptance}

Repository: {task["repository"]}
Worktree: {task["worktree_path"]}
Constraints: {constraints}
"""


def continuation_prompt(task: dict[str, Any], parent: dict[str, Any]) -> str:
    acceptance = (
        "\n".join(f"- {command}" for command in task["acceptance_commands"])
        or "- No acceptance commands configured"
    )
    return f"""Continue the shared Harbor session with a new task.

Previous Task: {parent["id"]} · {parent["title"]} ({parent["status"]})
New Harbor Task ID: {task["id"]}
New Task Title: {task["title"]}

Use the preceding conversation as context, but follow the new objective below.
Do not repeat completed work unless the new objective requires changing it.

New Objective:
{task["prompt"]}

Description:
{task.get("description") or "(none)"}

Current workspace:
{task["worktree_path"]}

Acceptance Criteria:
{acceptance}
"""


class Worker:
    def __init__(
        self,
        repository: HarborRepository,
        runtime: AgentRuntime,
        model_registry: ModelRegistry,
        worktrees: WorktreeManager,
        acceptance: AcceptanceRunner,
        config: dict[str, Any],
        data_dir: str | Path,
        worker_id: str | None = None,
    ):
        self.repository = repository
        self.runtime = runtime
        self.model_registry = model_registry
        self.worktrees = worktrees
        self.acceptance = acceptance
        self.config = config
        self.data_dir = Path(data_dir)
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._task_id: str | None = None

    async def _heartbeat(self) -> None:
        interval = float(self.config["scheduler"]["heartbeat_interval_seconds"])
        while True:
            self.repository.worker_heartbeat(
                self.worker_id, self._task_id, "RUNNING", os.getpid()
            )
            await asyncio.sleep(interval)

    def _resolve_config(self, task: dict[str, Any]) -> EffectiveAgentConfig:
        codex = self.config["codex"]
        profile = self.config.get("profiles", {}).get(task.get("profile") or "", {})
        return self.model_registry.resolve(
            task_model=task.get("model"),
            task_reasoning=task.get("reasoning_effort"),
            global_model=codex.get("default_model") or None,
            global_reasoning=codex.get("default_reasoning_effort", "medium"),
            profile=profile,
        )

    def _save_envelope(
        self,
        task: dict[str, Any],
        config: EffectiveAgentConfig,
        worktree: Path,
        head: str,
        stage: str,
        reason: str | None = None,
    ) -> RecoveryEnvelope:
        refreshed = self.repository.get_task(task["id"])
        envelope = RecoveryEnvelope.create(
            refreshed, str(worktree), head, config, stage, reason
        )
        envelope.write(self.data_dir / "tasks" / task["id"] / "recovery.json")
        return envelope

    async def _name_thread(
        self, task: dict[str, Any], thread_id: str, *, recovery: bool = False
    ) -> None:
        if not isinstance(self.runtime, CodexAppServerRuntime):
            return
        suffix = " · Recovery" if recovery else ""
        group = task.get("task_group")
        name = (
            f'[{group["id"]}] {group["title"]}{suffix}'
            if group and group.get("session_mode") == "shared"
            else f'[{task["id"]}] {task["title"]}{suffix}'
        )
        try:
            await self.runtime.client.thread_set_name(thread_id, name)
        except Exception as error:  # noqa: BLE001 - naming is optional metadata
            self.repository.add_event(
                task["id"],
                "CODEX_THREAD_NAME_FAILED",
                {"thread_id": thread_id, "error": str(error)[-1000:]},
            )

    def _quota_resume_at(self, error_type: ErrorType) -> str:
        quota_type = (
            "PRIMARY_5H"
            if error_type == ErrorType.RATE_LIMIT_5H
            else "WEEKLY"
        )
        now = datetime.now(UTC)
        for quota in self.repository.list_quotas():
            if quota["quota_type"] != quota_type or not quota.get("reset_at"):
                continue
            try:
                reset = datetime.fromisoformat(quota["reset_at"])
                if reset.tzinfo is None:
                    reset = reset.replace(tzinfo=UTC)
                if reset > now:
                    return reset.isoformat()
            except (TypeError, ValueError):
                pass
        # Avoid a hot loop if account/rateLimits telemetry lags the turn error.
        return (now + timedelta(seconds=60)).isoformat()

    async def _resolve_project(self, task: dict[str, Any]) -> str | None:
        if not isinstance(self.runtime, CodexAppServerRuntime):
            return task.get("codex_project_id")
        project_id = task.get("codex_project_id")
        if not project_id:
            registered = next(
                (
                    item
                    for item in self.repository.list_repositories()
                    if item["path"] == task["repository"]
                ),
                None,
            )
            project_id = registered.get("codex_project_id") if registered else None
        if not project_id:
            try:
                project = await self.runtime.client.find_project_for_path(
                    task.get("worktree_path") or task["repository"]
                )
                if project is None and task.get("worktree_path"):
                    project = await self.runtime.client.find_project_for_path(
                        task["repository"]
                    )
                project_id = project.get("id") if project else None
            except AppServerError as error:
                self.repository.add_event(
                    task["id"],
                    "CODEX_PROJECT_DISCOVERY_FAILED",
                    {"error": str(error)[-1000:]},
                )
                project_id = None
        if project_id:
            self.repository.set_repository_project(task["repository"], project_id)
            self.repository.set_task_project(task["id"], project_id)
            if task.get("origin_thread_id"):
                try:
                    await self.runtime.client.thread_update_metadata(
                        task["origin_thread_id"], project_id=project_id
                    )
                except AppServerError as error:
                    self.repository.add_event(
                        task["id"],
                        "ORIGIN_THREAD_PROJECT_BIND_FAILED",
                        {"error": str(error)[-1000:]},
                    )
        return project_id

    async def _prepare_context_and_workspace(
        self, task: dict[str, Any]
    ) -> tuple[dict[str, Any], Path]:
        parent: dict[str, Any] | None = None
        if task.get("session_parent_task_id"):
            parent = self.repository.get_task(task["session_parent_task_id"])
            if parent["status"] != TaskStatus.SUCCEEDED:
                raise GitError(
                    f"session parent {parent['id']} is not successful: {parent['status']}"
                )
            parent_thread = (
                parent.get("threads", [])[-1]["thread_id"]
                if parent.get("threads")
                else parent.get("root_thread_id")
            )
            if not parent_thread:
                raise GitError(f"session parent {parent['id']} has no Codex thread")
            project_id = task.get("codex_project_id") or parent.get(
                "codex_project_id"
            )
            self.repository.link_shared_thread(
                task["id"], parent_thread, parent["id"], project_id=project_id
            )
            task = self.repository.get_task(task["id"])

        mode = WorkspaceMode(task.get("workspace_mode") or WorkspaceMode.PROJECT)
        if task.get("worktree_path"):
            if mode == WorkspaceMode.ISOLATED and task.get("workspace_owned"):
                workspace = await self.worktrees.ensure(
                    task["id"], task["repository"], task["worktree_path"]
                )
            else:
                workspace = await self.worktrees.use_existing_workspace(
                    task["repository"], task["worktree_path"]
                )
            return task, workspace

        if mode == WorkspaceMode.INHERIT or task.get("reuse_parent_worktree"):
            if not parent or not parent.get("worktree_path"):
                raise GitError("inherited workspace requires a prepared parent task")
            workspace = await self.worktrees.use_existing_workspace(
                task["repository"], parent["worktree_path"]
            )
            self.repository.set_worktree(
                task["id"],
                str(workspace),
                owner_task_id=parent.get("worktree_owner_task_id") or parent["id"],
                owned=False,
            )
        elif mode == WorkspaceMode.PROJECT:
            candidate = task["repository"]
            if task.get("origin_thread_id") and isinstance(
                self.runtime, CodexAppServerRuntime
            ):
                try:
                    inspected = await self.runtime.inspect_thread(
                        task["origin_thread_id"]
                    )
                    origin = inspected.get("thread", inspected)
                    candidate = origin.get("cwd") or candidate
                except AppServerError as error:
                    self.repository.add_event(
                        task["id"],
                        "ORIGIN_WORKSPACE_READ_FAILED",
                        {"error": str(error)[-1000:]},
                    )
            workspace = await self.worktrees.use_existing_workspace(
                task["repository"], candidate
            )
            self.repository.set_worktree(task["id"], str(workspace), owned=False)
        else:
            workspace = await self.worktrees.ensure(
                task["id"], task["repository"], None
            )
            self.repository.set_worktree(task["id"], str(workspace), owned=True)
        return self.repository.get_task(task["id"]), workspace

    async def _start_or_resume(
        self,
        task: dict[str, Any],
        config: EffectiveAgentConfig,
        worktree: Path,
        envelope: RecoveryEnvelope,
        project_id: str | None,
    ) -> RuntimeTurnResult:
        threads = task.get("threads", [])
        active_thread = (
            threads[-1]["thread_id"] if threads else task.get("root_thread_id")
        )
        if active_thread:
            parent = (
                self.repository.get_task(task["session_parent_task_id"])
                if task.get("session_parent_task_id")
                and int(task.get("current_attempt", 0)) == 0
                else None
            )
            prompt = (
                continuation_prompt(task, parent)
                if parent
                else build_recovery_prompt(envelope)
            )
            try:
                if project_id and isinstance(self.runtime, CodexAppServerRuntime):
                    await self.runtime.client.thread_update_metadata(
                        active_thread, project_id=project_id
                    )
                await self._name_thread(task, active_thread)
                result = await self.runtime.resume_task(
                    active_thread, str(worktree), prompt, config
                )
                self.repository.add_event(
                    task["id"],
                    "CODEX_THREAD_RESUMED",
                    {"thread_id": active_thread},
                )
                return result
            except AppServerError:
                if isinstance(self.runtime, CodexAppServerRuntime):
                    try:
                        forked = await self.runtime.client.thread_fork(
                            active_thread,
                            cwd=str(worktree),
                            model=config.effective_model,
                        )
                        thread = forked.get("thread", forked)
                        fork_id = str(thread.get("id") or thread.get("threadId"))
                        self.repository.set_thread(
                            task["id"],
                            fork_id,
                            ThreadRole.RECOVERY,
                            parent_thread_id=active_thread,
                            model=config.effective_model,
                            project_id=project_id,
                        )
                        if project_id:
                            await self.runtime.client.thread_update_metadata(
                                fork_id, project_id=project_id
                            )
                        await self._name_thread(task, fork_id, recovery=True)
                        envelope.thread_id = fork_id
                        envelope.write(
                            self.data_dir / "tasks" / task["id"] / "recovery.json"
                        )
                        return await self.runtime.start_turn(
                            fork_id, str(worktree), prompt, config
                        )
                    except AppServerError:
                        pass
        if isinstance(self.runtime, CodexAppServerRuntime):
            started = await self.runtime.client.thread_start(
                cwd=str(worktree),
                model=config.effective_model,
                approval_policy=self.runtime.approval_policy,
                sandbox=self.runtime.sandbox,
                project_id=project_id,
                runtime_workspace_roots=[str(worktree)],
            )
            thread = started.get("thread", started)
            thread_id = str(thread.get("id") or thread.get("threadId"))
            role = (
                ThreadRole.ROOT
                if not task.get("root_thread_id")
                else ThreadRole.RECOVERY
            )
            self.repository.set_thread(
                task["id"],
                thread_id,
                role,
                model=config.effective_model,
                project_id=project_id,
            )
            await self._name_thread(
                task, thread_id, recovery=role == ThreadRole.RECOVERY
            )
            envelope.thread_id = thread_id
            envelope.write(self.data_dir / "tasks" / task["id"] / "recovery.json")
            return await self.runtime.start_turn(
                thread_id, str(worktree), initial_prompt(task), config
            )
        result = await self.runtime.start_task(
            str(worktree), initial_prompt(task), config
        )
        self.repository.set_thread(
            task["id"], result.thread_id, ThreadRole.ROOT, model=config.effective_model
        )
        return result

    async def _handle_failure(
        self, task: dict[str, Any], attempt: int, error: Exception | str
    ) -> None:
        message = str(error)
        error_type = classify_error(message)
        self.repository.finish_attempt(
            task["id"],
            attempt,
            (
                "WAIT_QUOTA"
                if error_type
                in {ErrorType.RATE_LIMIT_5H, ErrorType.RATE_LIMIT_WEEKLY}
                else "FAILED"
            ),
            error_type=error_type,
            error_message=message[-8000:],
        )
        if error_type in {ErrorType.RATE_LIMIT_5H, ErrorType.RATE_LIMIT_WEEKLY}:
            resume_at = self._quota_resume_at(error_type)
            self.repository.transition(
                task["id"],
                TaskStatus.WAIT_QUOTA,
                reason=error_type,
                resume_at=resume_at,
            )
            self.repository.add_event(
                task["id"],
                "TASK_RATE_LIMITED",
                {
                    "attempt": attempt,
                    "error_type": error_type,
                    "resume_at": resume_at,
                },
            )
        elif error_type in {ErrorType.AUTH, ErrorType.GIT}:
            self.repository.transition(
                task["id"], TaskStatus.BLOCKED, reason=error_type
            )
        else:
            failure_count = self.repository.record_failure(task["id"])
            if failure_count >= int(task["max_attempts"]):
                self.repository.transition(
                    task["id"], TaskStatus.FAILED, reason=error_type
                )
            else:
                delay = min(600, 30 * (2 ** max(0, failure_count - 1)))
                resume_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
                self.repository.transition(
                    task["id"],
                    TaskStatus.RETRY_WAIT,
                    reason=error_type,
                    resume_at=resume_at,
                )

    async def run(self, task: dict[str, Any]) -> None:
        self._task_id = task["id"]
        self.repository.worker_heartbeat(
            self.worker_id, self._task_id, "STARTING", os.getpid()
        )
        self.repository.add_event(
            task["id"], "WORKER_STARTED", {"worker_id": self.worker_id}
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        attempt = 0
        try:
            try:
                config = self._resolve_config(task)
            except ModelValidationError as error:
                self.repository.transition(
                    task["id"], TaskStatus.BLOCKED, reason=error.error_type
                )
                return
            try:
                task, worktree = await self._prepare_context_and_workspace(task)
            except GitError as error:
                self.repository.transition(
                    task["id"], TaskStatus.BLOCKED, reason=ErrorType.GIT
                )
                self.repository.add_event(
                    task["id"], "TASK_FAILED", {"error": str(error)}
                )
                return
            task = self.repository.get_task(task["id"])
            project_id = await self._resolve_project(task)
            task = self.repository.get_task(task["id"])
            head = await self.worktrees.head(worktree)
            envelope = self._save_envelope(
                task, config, worktree, head, "starting turn"
            )
            self.repository.set_claim_running(task["id"])

            first_turn_in_worker = True
            while True:
                self.repository.apply_pending_agent_config(task["id"])
                task = self.repository.get_task(task["id"])
                config = self._resolve_config(task)
                attempt = self.repository.create_attempt(
                    task["id"], config, task.get("root_thread_id")
                )
                try:
                    if first_turn_in_worker or task.get("root_thread_id") is None:
                        result = await self._start_or_resume(
                            task, config, worktree, envelope, project_id
                        )
                    else:
                        thread_id = task.get("threads", [])[-1]["thread_id"]
                        prompt = (
                            envelope.stage
                            if envelope.stage.startswith("Acceptance failed")
                            else build_recovery_prompt(envelope)
                        )
                        result = await self.runtime.start_turn(
                            thread_id, str(worktree), prompt, config
                        )
                    self.repository.bind_attempt_thread(
                        task["id"], attempt, result.thread_id, result.turn_id
                    )
                    first_turn_in_worker = False
                    if result.status.lower() not in {
                        "completed",
                        "succeeded",
                        "success",
                    }:
                        raise RuntimeError(
                            result.error
                            or f"Codex turn ended with status {result.status}"
                        )
                except Exception as error:  # noqa: BLE001 - classify all runtime/backend failures
                    task = self.repository.get_task(task["id"])
                    if task["status"] == TaskStatus.CANCELLED:
                        return
                    await self._handle_failure(task, attempt, error)
                    return

                if (
                    self.repository.get_task(task["id"])["status"]
                    == TaskStatus.CANCELLED
                ):
                    return

                self.repository.finish_attempt(task["id"], attempt, "CODEX_COMPLETED")
                head = await self.worktrees.head(worktree)
                envelope = self._save_envelope(
                    task, config, worktree, head, "running acceptance"
                )
                acceptance = await self.acceptance.run(
                    task["acceptance_commands"], worktree
                )
                if acceptance.passed:
                    self.repository.transition(task["id"], TaskStatus.SUCCEEDED)
                    self.repository.add_event(
                        task["id"], "TASK_COMPLETED", {"attempt": attempt}
                    )
                    self.repository.finish_attempt(task["id"], attempt, "SUCCEEDED")
                    return
                self.repository.finish_attempt(
                    task["id"],
                    attempt,
                    "ACCEPTANCE_FAILED",
                    error_type=ErrorType.ACCEPTANCE,
                )
                refreshed = self.repository.get_task(task["id"])
                failure_count = self.repository.record_failure(task["id"])
                if failure_count >= refreshed["max_attempts"]:
                    self.repository.transition(
                        task["id"], TaskStatus.FAILED, reason=ErrorType.ACCEPTANCE
                    )
                    return
                envelope = self._save_envelope(
                    refreshed,
                    config,
                    worktree,
                    head,
                    acceptance.failure_prompt(),
                    str(ErrorType.ACCEPTANCE),
                )
        finally:
            self.repository.clear_claim(task["id"])
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            self.repository.remove_worker(self.worker_id)
