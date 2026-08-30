from pathlib import Path

from codex_harbor.domain import PoolStatus, TaskSpec, TaskStatus


def add(repository, git_repo: Path, title: str, **kwargs):
    return repository.create_task(
        TaskSpec(title=title, repository=str(git_repo), prompt=title, **kwargs)
    )


def test_persistent_crud_events_and_dependency(repository, git_repo):
    first = add(repository, git_repo, "first", task_id="T001")
    second = add(repository, git_repo, "second", task_id="T002", depends_on=["T001"])
    assert first["status"] == TaskStatus.READY
    assert second["status"] == TaskStatus.WAIT_DEP
    claimed = repository.claim_next("worker-1")
    assert claimed["id"] == "T001"
    repository.transition("T001", TaskStatus.RUNNING)
    repository.transition("T001", TaskStatus.SUCCEEDED)
    assert repository.refresh_dependencies() == 1
    assert repository.get_task("T002")["status"] == TaskStatus.READY
    assert any(
        event["event_type"] == "TASK_CREATED"
        for event in repository.list_events("T001")
    )


def test_priority_fifo_and_exclusive_group(repository, git_repo):
    add(repository, git_repo, "low", task_id="T001", priority=200)
    add(
        repository,
        git_repo,
        "high-a",
        task_id="T002",
        priority=10,
        exclusive_group="parser",
    )
    add(
        repository,
        git_repo,
        "high-b",
        task_id="T003",
        priority=10,
        exclusive_group="parser",
    )
    first = repository.claim_next("one")
    assert first["id"] == "T002"
    repository.transition(first["id"], TaskStatus.RUNNING)
    second = repository.claim_next("two")
    assert second["id"] == "T001"


def test_weekly_drain_preserves_ready_and_freezes_after_grandfathered(
    repository, git_repo
):
    add(repository, git_repo, "running", task_id="T001")
    add(repository, git_repo, "ready", task_id="T002")
    repository.claim_next("one")
    repository.transition("T001", TaskStatus.RUNNING)
    repository.begin_weekly_drain("week-2")
    assert repository.get_pool()["state"] == PoolStatus.DRAINING
    assert repository.get_task("T001")["grandfathered"] == 1
    assert repository.get_task("T002")["status"] == TaskStatus.READY
    assert repository.claim_next("two", grandfathered_only=True) is None
    repository.transition("T001", TaskStatus.SUCCEEDED)
    assert repository.freeze_if_drained()
    assert repository.get_pool()["state"] == PoolStatus.FROZEN
    assert repository.get_task("T002")["status"] == TaskStatus.READY


def test_running_agent_change_is_pending_until_next_turn(repository, git_repo):
    add(
        repository,
        git_repo,
        "agent",
        task_id="T001",
        model="model-a",
        reasoning_effort="high",
    )
    repository.claim_next("one")
    repository.transition("T001", TaskStatus.RUNNING)
    current = repository.update_agent_config("T001", model="model-b", reasoning="xhigh")
    assert current["model"] == "model-a"
    assert current["pending_model"] == "model-b"
    repository.apply_pending_agent_config("T001")
    applied = repository.get_task("T001")
    assert applied["model"] == "model-b" and applied["reasoning_effort"] == "xhigh"


def test_partial_agent_change_preserves_other_field_and_can_clear_inheritance(
    repository, git_repo
):
    add(
        repository,
        git_repo,
        "agent",
        task_id="T001",
        model="model-a",
        reasoning_effort="high",
    )
    changed = repository.update_agent_config("T001", reasoning="low")
    assert changed["model"] == "model-a" and changed["reasoning_effort"] == "low"
    repository.claim_next("one")
    repository.transition("T001", TaskStatus.RUNNING)
    pending = repository.update_agent_config("T001", model=None)
    assert pending["model"] == "model-a" and pending["pending_model_set"] == 1
    repository.apply_pending_agent_config("T001")
    assert repository.get_task("T001")["model"] is None
