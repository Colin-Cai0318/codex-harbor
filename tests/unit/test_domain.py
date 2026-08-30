import pytest

from codex_harbor.domain import InvalidTransition, TaskStatus, validate_transition


def test_state_machine_accepts_main_path():
    validate_transition(TaskStatus.CREATED, TaskStatus.PENDING)
    validate_transition(TaskStatus.PENDING, TaskStatus.READY)
    validate_transition(TaskStatus.READY, TaskStatus.CLAIMED)
    validate_transition(TaskStatus.CLAIMED, TaskStatus.RUNNING)
    validate_transition(TaskStatus.RUNNING, TaskStatus.SUCCEEDED)


def test_state_machine_rejects_shortcut():
    with pytest.raises(InvalidTransition):
        validate_transition(TaskStatus.CREATED, TaskStatus.SUCCEEDED)
