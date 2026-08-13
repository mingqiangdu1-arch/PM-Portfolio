import pytest

from app.domain.task_state import ALLOWED_TRANSITIONS, InvalidTaskTransition, TaskStatus, transition


def test_happy_path_ends_as_candidate_ready() -> None:
    path = [
        TaskStatus.PRECHECKING,
        TaskStatus.QUEUED,
        TaskStatus.PREPARING,
        TaskStatus.GENERATING,
        TaskStatus.CHECKING,
        TaskStatus.READY,
    ]
    for source, target in zip(path, path[1:]):
        assert transition(source, target).target == target


def test_cancel_requires_acknowledgement() -> None:
    assert transition(TaskStatus.QUEUED, TaskStatus.CANCEL_REQUESTED).target == TaskStatus.CANCEL_REQUESTED
    assert transition(TaskStatus.CANCEL_REQUESTED, TaskStatus.CANCELLED).target == TaskStatus.CANCELLED


def test_terminal_statuses_have_no_outbound_transition() -> None:
    for status in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.EXPIRED, TaskStatus.STALE_TARGET):
        assert not ALLOWED_TRANSITIONS[status]


def test_formalization_is_not_an_ai_task_state() -> None:
    assert "formal" not in {status.value for status in TaskStatus}
    with pytest.raises(InvalidTaskTransition):
        transition(TaskStatus.READY, TaskStatus.QUEUED)
