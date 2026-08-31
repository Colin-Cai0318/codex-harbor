from __future__ import annotations

import asyncio
from pathlib import Path

from ..storage.repository import HarborRepository


class GitError(RuntimeError):
    pass


class WorktreeManager:
    def __init__(self, repository: HarborRepository, root: str | Path):
        self.repository = repository
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def _git(self, repo: Path, *args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode:
            raise GitError(
                stderr.decode(errors="replace").strip() or "git command failed"
            )
        return stdout.decode(errors="replace").strip()

    async def validate_repository(self, path: str | Path) -> Path:
        repo = Path(path).expanduser().resolve()
        if not self.repository.is_registered_repository(repo):
            raise GitError(f"repository is not registered: {repo}")
        root = Path(await self._git(repo, "rev-parse", "--show-toplevel")).resolve()
        if root != repo:
            raise GitError(
                f"registered path is not the Git root: {repo} (root: {root})"
            )
        await self._git(repo, "rev-parse", "--verify", "HEAD")
        return repo

    async def ensure(
        self, task_id: str, repository: str | Path, existing: str | None = None
    ) -> Path:
        repo = await self.validate_repository(repository)
        if existing:
            current = Path(existing).resolve()
            if current.is_dir() and self.root in current.parents:
                validated = await self.use_existing_workspace(repo, current)
                if validated != current:
                    raise GitError(
                        f"owned worktree path is not a Git root: {current}"
                    )
                return validated
        target = (self.root / task_id).resolve()
        if self.root not in target.parents:
            raise GitError("worktree path escaped Harbor worktree root")
        if target.exists():
            validated = await self.use_existing_workspace(repo, target)
            if validated != target:
                raise GitError(f"owned worktree path is not a Git root: {target}")
            return validated
        branch = f"harbor/{task_id}"
        branch_exists = False
        try:
            await self._git(
                repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"
            )
            branch_exists = True
        except GitError:
            pass
        args = (
            ("worktree", "add", str(target), branch)
            if branch_exists
            else ("worktree", "add", "-b", branch, str(target), "HEAD")
        )
        await self._git(repo, *args)
        return target

    async def use_existing_workspace(
        self, repository: str | Path, workspace: str | Path
    ) -> Path:
        repo = await self.validate_repository(repository)
        candidate = Path(workspace).expanduser().resolve()
        if not candidate.is_dir():
            raise GitError(f"existing workspace does not exist: {candidate}")
        top = Path(
            await self._git(candidate, "rev-parse", "--show-toplevel")
        ).resolve()

        async def common_dir(path: Path) -> Path:
            value = Path(await self._git(path, "rev-parse", "--git-common-dir"))
            return (path / value).resolve() if not value.is_absolute() else value.resolve()

        if await common_dir(top) != await common_dir(repo):
            raise GitError(
                f"workspace does not belong to registered repository: {top}"
            )
        return top

    async def head(self, worktree: str | Path) -> str:
        return await self._git(Path(worktree), "rev-parse", "HEAD")

    async def diff(self, worktree: str | Path) -> str:
        return await self._git(Path(worktree), "status", "--short")

    async def cleanup(
        self, task_id: str, repository: str | Path, worktree: str | Path
    ) -> None:
        repo = await self.validate_repository(repository)
        target = Path(worktree).resolve()
        expected = (self.root / task_id).resolve()
        if target != expected or self.root not in target.parents:
            raise GitError("refusing to remove a worktree outside the owned task path")
        await self._git(repo, "worktree", "remove", str(target))
