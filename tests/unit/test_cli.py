from __future__ import annotations

from pathlib import Path

from codex_harbor.cli import build_parser, dispatch
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
