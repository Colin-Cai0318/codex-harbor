from __future__ import annotations

import subprocess

import pytest

from codex_harbor.git import GitError, WorktreeManager


@pytest.mark.asyncio
async def test_unregistered_or_nested_repository_is_rejected(repository, git_repo, tmp_path):
    manager = WorktreeManager(repository, tmp_path / "worktrees")
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()
    with pytest.raises(GitError, match="not registered"):
        await manager.validate_repository(unregistered)

    nested = git_repo / "nested"
    nested.mkdir()
    repository.add_repository(nested)
    with pytest.raises(GitError, match="not the Git root"):
        await manager.validate_repository(nested)


@pytest.mark.asyncio
async def test_conflicting_existing_directory_is_not_reused(repository, git_repo, tmp_path):
    worktrees = tmp_path / "worktrees"
    conflicting = worktrees / "T001"
    conflicting.mkdir(parents=True)
    (conflicting / "unrelated.txt").write_text("not a worktree", encoding="utf-8")
    manager = WorktreeManager(repository, worktrees)
    with pytest.raises(GitError):
        await manager.ensure("T001", git_repo)


@pytest.mark.asyncio
async def test_workspace_from_another_repository_and_unsafe_cleanup_are_rejected(
    repository, git_repo, tmp_path
):
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=other, check=True, capture_output=True)
    manager = WorktreeManager(repository, tmp_path / "worktrees")
    with pytest.raises(GitError, match="does not belong"):
        await manager.use_existing_workspace(git_repo, other)
    with pytest.raises(GitError, match="refusing to remove"):
        await manager.cleanup("T001", git_repo, git_repo)


@pytest.mark.asyncio
async def test_missing_workspace_and_git_command_failure_are_reported(
    repository, git_repo, tmp_path
):
    manager = WorktreeManager(repository, tmp_path / "worktrees")
    with pytest.raises(GitError, match="does not exist"):
        await manager.use_existing_workspace(git_repo, tmp_path / "missing")
    with pytest.raises(GitError):
        await manager._git(git_repo, "rev-parse", "--verify", "MISSING-REF")
