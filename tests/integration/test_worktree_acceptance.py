import pytest

from codex_harbor.acceptance import AcceptanceRunner
from codex_harbor.domain import TaskSpec
from codex_harbor.execution import select_backend
from codex_harbor.git import WorktreeManager


@pytest.mark.asyncio
async def test_creates_isolated_worktree_and_runs_acceptance(
    repository, git_repo, tmp_path
):
    task = repository.create_task(
        TaskSpec(title="worktree", repository=str(git_repo), prompt="worktree")
    )
    manager = WorktreeManager(repository, tmp_path / "worktrees")
    worktree = await manager.ensure(task["id"], git_repo)
    assert worktree.is_dir()
    assert worktree != git_repo
    result = await AcceptanceRunner(select_backend("local"), timeout=30).run(
        ["git rev-parse --is-inside-work-tree"], worktree
    )
    assert result.passed
    assert result.commands[0].stdout.strip() == "true"


@pytest.mark.asyncio
async def test_acceptance_stops_on_first_failure(git_repo):
    result = await AcceptanceRunner(select_backend("local"), timeout=30).run(
        ["git rev-parse --verify DOES_NOT_EXIST", "git status"], git_repo
    )
    assert not result.passed
    assert len(result.commands) == 1
