from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..domain import EffectiveAgentConfig, utc_now


@dataclass(slots=True)
class RecoveryEnvelope:
    task_id: str
    objective: str
    thread_id: str | None
    worktree: str
    git_head: str
    attempt: int
    stage: str
    last_reason: str | None
    agent: dict
    acceptance: list[str]
    updated_at: str

    @classmethod
    def create(
        cls,
        task: dict,
        worktree: str,
        git_head: str,
        config: EffectiveAgentConfig,
        stage: str,
        last_reason: str | None = None,
    ) -> RecoveryEnvelope:
        return cls(
            task_id=task["id"],
            objective=task["prompt"],
            thread_id=task.get("root_thread_id"),
            worktree=worktree,
            git_head=git_head,
            attempt=int(task.get("current_attempt", 0)),
            stage=stage,
            last_reason=last_reason,
            agent={
                "requested_model": config.requested_model,
                "requested_reasoning_effort": config.requested_reasoning_effort,
                "last_effective_model": config.effective_model,
                "last_effective_reasoning_effort": config.effective_reasoning_effort,
            },
            acceptance=task.get("acceptance_commands", []),
            updated_at=utc_now(),
        )

    def write(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(target)


def build_recovery_prompt(envelope: RecoveryEnvelope) -> str:
    acceptance = (
        "\n".join(f"- {command}" for command in envelope.acceptance)
        or "- No commands configured"
    )
    return f"""Resume Harbor Task {envelope.task_id}.

Do not restart the task from the beginning.

Objective:
{envelope.objective}

Existing worktree:
{envelope.worktree}

Known Git HEAD:
{envelope.git_head}

Current known stage:
{envelope.stage}

Inspect git status and git diff first. Continue from the existing implementation.

Acceptance criteria:
{acceptance}
"""
