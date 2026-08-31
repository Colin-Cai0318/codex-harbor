from __future__ import annotations

from pathlib import Path

import pytest

from codex_harbor.cli import build_parser, dispatch
from codex_harbor.domain import QuotaWindow
from codex_harbor.storage import Database, HarborRepository


def test_group_import_creates_shared_chain_in_existing_workspace(
    tmp_path: Path, git_repo: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "harbor-data"
    monkeypatch.setenv("HARBOR_DATA_DIR", str(data_dir))
    parser = build_parser()
    assert dispatch(parser.parse_args(["repo", "add", str(git_repo)])) == 0
    definition = tmp_path / "group.yaml"
    definition.write_text(
        f"""title: shared chain
repository:
  path: {git_repo.as_posix()}
session_mode: shared
workspace_mode: project
sequential: true
tasks:
  - title: database
    prompt: change the database
  - title: scheduler
    prompt: continue with the scheduler
""",
        encoding="utf-8",
    )

    assert dispatch(parser.parse_args(["task", "group-import", str(definition)])) == 0

    repository = HarborRepository(Database(data_dir / "harbor.db"))
    group = repository.list_task_groups()[0]
    first, second = group["tasks"]
    assert group["session_mode"] == "shared"
    assert first["workspace_mode"] == "project"
    assert second["workspace_mode"] == "inherit"
    assert second["session_parent_task_id"] == first["id"]
    assert second["depends_on"] == [first["id"]]


def test_cli_control_and_inspection_paths_report_remaining_quota(
    tmp_path: Path, git_repo: Path, monkeypatch, capsys
) -> None:
    data_dir = tmp_path / "harbor-data"
    monkeypatch.setenv("HARBOR_DATA_DIR", str(data_dir))
    parser = build_parser()

    assert dispatch(parser.parse_args(["init"])) == 0
    assert dispatch(parser.parse_args(["repo", "add", str(git_repo)])) == 0
    assert dispatch(parser.parse_args(["repo", "list"])) == 0
    assert dispatch(
        parser.parse_args(
            [
                "task",
                "add",
                "--id",
                "T001",
                "--repo",
                str(git_repo),
                "--title",
                "CLI fault simulation",
                "--model",
                "model-a",
            ]
        )
    ) == 0
    assert dispatch(parser.parse_args(["task", "list"])) == 0
    assert dispatch(parser.parse_args(["task", "show", "T001"])) == 0
    assert dispatch(parser.parse_args(["task", "config", "T001", "--reasoning", "low"])) == 0

    repository = HarborRepository(Database(data_dir / "harbor.db"))
    repository.save_quota(
        "codex", QuotaWindow("PRIMARY_5H", used_percent=25, remaining=75, source="test")
    )
    assert dispatch(parser.parse_args(["ps"])) == 0
    output = capsys.readouterr().out
    assert "75% remaining" in output
    assert "25% used" not in output
    assert dispatch(parser.parse_args(["quota"])) == 0
    assert dispatch(parser.parse_args(["pause"])) == 0
    assert dispatch(parser.parse_args(["freeze"])) == 0
    assert dispatch(parser.parse_args(["resume"])) == 0
    assert dispatch(parser.parse_args(["logs", "T001"])) == 0
    assert dispatch(parser.parse_args(["history", "T001"])) == 0
    assert dispatch(parser.parse_args(["task", "cancel", "T001"])) == 0
    assert dispatch(parser.parse_args(["task", "retry", "T001"])) == 0


def test_cli_import_and_invalid_input_boundaries(
    tmp_path: Path, git_repo: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "harbor-data"
    monkeypatch.setenv("HARBOR_DATA_DIR", str(data_dir))
    parser = build_parser()
    dispatch(parser.parse_args(["repo", "add", str(git_repo)]))
    imported = tmp_path / "tasks.yaml"
    imported.write_text(
        f"title: imported\nrepository: {git_repo.as_posix()}\nprompt: test\n",
        encoding="utf-8",
    )
    assert dispatch(parser.parse_args(["task", "import", str(imported)])) == 0

    with pytest.raises(ValueError, match="provide --model"):
        dispatch(parser.parse_args(["task", "config", "T001"]))
    with pytest.raises(ValueError, match="no worktree"):
        dispatch(parser.parse_args(["task", "cleanup", "T001"]))

    invalid = tmp_path / "invalid-group.yaml"
    invalid.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        dispatch(parser.parse_args(["task", "group-import", str(invalid)]))
    invalid.write_text("title: empty\nrepository: {}\ntasks: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repository path is required"):
        dispatch(parser.parse_args(["task", "group-import", str(invalid)]))
    invalid.write_text(
        f"title: empty\nrepository: {git_repo.as_posix()}\ntasks: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-empty tasks"):
        dispatch(parser.parse_args(["task", "group-import", str(invalid)]))
