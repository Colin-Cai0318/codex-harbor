from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..events import sanitize
from ..execution import ExecutionBackend


@dataclass(slots=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class AcceptanceResult:
    passed: bool
    commands: list[CommandResult] = field(default_factory=list)

    def failure_prompt(self) -> str:
        failed = next((item for item in self.commands if item.exit_code), None)
        if not failed:
            return "Acceptance failed without command output. Inspect the repository and continue."
        return (
            "Acceptance failed.\n\n"
            f"Command:\n{failed.command}\n\n"
            f"Exit code: {failed.exit_code}\n\n"
            f"Output:\n{failed.stdout[-8000:]}\n{failed.stderr[-8000:]}\n\n"
            "Fix the implementation and rerun the acceptance criteria."
        )


class AcceptanceRunner:
    def __init__(self, backend: ExecutionBackend, *, timeout: float = 1800):
        self.backend = backend
        self.timeout = timeout

    async def run(self, commands: list[str], cwd: str | Path) -> AcceptanceResult:
        results: list[CommandResult] = []
        for command in commands:
            code, stdout, stderr = await self.backend.run(command, cwd, self.timeout)
            results.append(
                CommandResult(command, code, sanitize(stdout), sanitize(stderr))
            )
            if code:
                return AcceptanceResult(False, results)
        return AcceptanceResult(True, results)
