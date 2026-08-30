from __future__ import annotations

import copy
import subprocess
from pathlib import Path

import pytest

from codex_harbor.config import DEFAULTS
from codex_harbor.domain import utc_now
from codex_harbor.storage import Database, HarborRepository


@pytest.fixture
def config_values() -> dict:
    values = copy.deepcopy(DEFAULTS)
    values["scheduler"]["heartbeat_interval_seconds"] = 0.01
    values["scheduler"]["poll_interval_seconds"] = 0.01
    return values


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    path = tmp_path / "project"
    path.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "harbor-tests@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Harbor Tests"], cwd=path, check=True)
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"], cwd=path, check=True, capture_output=True
    )
    return path.resolve()


@pytest.fixture
def repository(tmp_path: Path, git_repo: Path) -> HarborRepository:
    database = Database(tmp_path / "data" / "harbor.db")
    database.migrate(freeze_on_weekly_reset=True, now=utc_now())
    repo = HarborRepository(database)
    repo.add_repository(git_repo)
    return repo
