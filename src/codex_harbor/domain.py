from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    WAIT_DEP = "WAIT_DEP"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    WAIT_QUOTA = "WAIT_QUOTA"
    RETRY_WAIT = "RETRY_WAIT"
    BLOCKED = "BLOCKED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PoolStatus(StrEnum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DRAINING = "DRAINING"
    FROZEN = "FROZEN"


class ThreadRole(StrEnum):
    ROOT = "ROOT"
    FORK = "FORK"
    RECOVERY = "RECOVERY"
    SUBAGENT = "SUBAGENT"
    REVIEW = "REVIEW"


class SessionMode(StrEnum):
    ISOLATED = "isolated"
    SHARED = "shared"


class WorkspaceMode(StrEnum):
    PROJECT = "project"
    ISOLATED = "isolated"
    INHERIT = "inherit"


class ErrorType(StrEnum):
    RATE_LIMIT_5H = "RATE_LIMIT_5H"
    RATE_LIMIT_WEEKLY = "RATE_LIMIT_WEEKLY"
    NETWORK = "NETWORK"
    AUTH = "AUTH"
    APP_SERVER = "APP_SERVER"
    MCP = "MCP"
    GIT = "GIT"
    PROCESS = "PROCESS"
    ACCEPTANCE = "ACCEPTANCE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_CONFIG_INVALID = "MODEL_CONFIG_INVALID"
    REASONING_NOT_SUPPORTED = "REASONING_NOT_SUPPORTED"
    AGENT_FAILURE = "AGENT_FAILURE"
    UPSTREAM_FAILED = "UPSTREAM_FAILED"
    UNKNOWN = "UNKNOWN"


TERMINAL_TASK_STATES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.BLOCKED,
}

ACTIVE_TASK_STATES = {
    TaskStatus.CLAIMED,
    TaskStatus.RUNNING,
    TaskStatus.WAIT_QUOTA,
    TaskStatus.RETRY_WAIT,
}

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PENDING, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.PENDING: {
        TaskStatus.WAIT_DEP,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.WAIT_DEP: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.READY: {TaskStatus.CLAIMED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.CLAIMED: {
        TaskStatus.RUNNING,
        TaskStatus.READY,
        TaskStatus.RETRY_WAIT,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.SUCCEEDED,
        TaskStatus.WAIT_QUOTA,
        TaskStatus.RETRY_WAIT,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.WAIT_QUOTA: {
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RETRY_WAIT: {
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.WAIT_DEP,
        TaskStatus.READY,
        TaskStatus.CANCELLED,
    },
    TaskStatus.FAILED: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.CANCELLED: {TaskStatus.READY},
}


@dataclass(slots=True)
class TaskSpec:
    title: str
    repository: str
    prompt: str
    description: str = ""
    task_id: str | None = None
    execution_backend: str = "local"
    priority: int = 100
    depends_on: list[str] = field(default_factory=list)
    exclusive_group: str | None = None
    acceptance_commands: list[str] = field(default_factory=list)
    max_attempts: int = 5
    model: str | None = None
    reasoning_effort: str | None = None
    profile: str | None = None
    task_group_id: str | None = None
    codex_project_id: str | None = None
    origin_thread_id: str | None = None
    session_parent_task_id: str | None = None
    reuse_parent_worktree: bool = False
    workspace_mode: WorkspaceMode = WorkspaceMode.PROJECT


@dataclass(slots=True)
class EffectiveAgentConfig:
    requested_model: str | None
    requested_reasoning_effort: str | None
    effective_model: str | None
    effective_reasoning_effort: str


@dataclass(slots=True)
class QuotaWindow:
    quota_type: str
    available: bool = True
    used_percent: float | None = None
    remaining: float | None = None
    reset_at: str | None = None
    window_id: str | None = None
    source: str = "unknown"
    updated_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class RuntimeTurnResult:
    thread_id: str
    turn_id: str | None
    status: str
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class InvalidTransition(ValueError):
    pass


def validate_transition(old: str | TaskStatus, new: str | TaskStatus) -> None:
    old_state, new_state = TaskStatus(old), TaskStatus(new)
    if new_state not in ALLOWED_TRANSITIONS[old_state]:
        raise InvalidTransition(f"invalid task transition: {old_state} -> {new_state}")
