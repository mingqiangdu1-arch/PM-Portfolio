from dataclasses import dataclass, field

import pytest

from app.tasking.ports import SubmitTaskCommand
from app.tasking.service import NewTaskRejected, TaskDispatchFailed, TaskSubmissionService


@dataclass
class StoreFake:
    created: list[SubmitTaskCommand] = field(default_factory=list)
    dispatch_failures: list[tuple[str, str]] = field(default_factory=list)
    cancellations: list[tuple[str, str]] = field(default_factory=list)
    cancel_dispatch_failures: list[tuple[str, str]] = field(default_factory=list)

    def create_queued_task(self, command: SubmitTaskCommand) -> None:
        self.created.append(command)

    def record_dispatch_failure(self, task_public_id: str, reason_code: str) -> None:
        self.dispatch_failures.append((task_public_id, reason_code))

    def request_cancel(self, task_public_id: str, command_id: str) -> None:
        self.cancellations.append((task_public_id, command_id))

    def record_cancel_dispatch_failure(self, task_public_id: str, reason_code: str) -> None:
        self.cancel_dispatch_failures.append((task_public_id, reason_code))


@dataclass
class QueueFake:
    available: bool = True
    fail_enqueue: bool = False
    fail_cancel: bool = False
    enqueued: list[tuple[str, str]] = field(default_factory=list)

    def ensure_available(self) -> None:
        if not self.available:
            raise ConnectionError("Redis unavailable")

    def enqueue(self, task_public_id: str, trace_id: str) -> None:
        if self.fail_enqueue:
            raise ConnectionError("dispatch failed")
        self.enqueued.append((task_public_id, trace_id))

    def request_cancel(self, task_public_id: str, trace_id: str) -> None:
        if self.fail_cancel:
            raise ConnectionError("cancel dispatch failed")


def command() -> SubmitTaskCommand:
    return SubmitTaskCommand("task-1", "trace-1", "command-1", "flow.generate")


def test_queue_after_durable_create() -> None:
    store, queue = StoreFake(), QueueFake()
    assert TaskSubmissionService(store, queue).submit(command()) == "queued"
    assert store.created == [command()]
    assert queue.enqueued == [("task-1", "trace-1")]


def test_redis_unavailable_rejects_before_creating_task() -> None:
    store, queue = StoreFake(), QueueFake(available=False)
    with pytest.raises(NewTaskRejected) as caught:
        TaskSubmissionService(store, queue).submit(command())
    assert caught.value.reason_code == "broker_unavailable"
    assert store.created == []


def test_dispatch_race_records_durable_failure() -> None:
    store, queue = StoreFake(), QueueFake(fail_enqueue=True)
    with pytest.raises(TaskDispatchFailed):
        TaskSubmissionService(store, queue).submit(command())
    assert store.created == [command()]
    assert store.dispatch_failures == [("task-1", "dispatch_failed_after_durable_create")]


def test_cancel_request_stays_durable_when_dispatch_is_deferred() -> None:
    store, queue = StoreFake(), QueueFake(fail_cancel=True)
    outcome = TaskSubmissionService(store, queue).cancel("task-1", "trace-1", "cancel-command-1")
    assert outcome.status == "cancel_requested"
    assert outcome.dispatch_deferred is True
    assert store.cancellations == [("task-1", "cancel-command-1")]
    assert store.cancel_dispatch_failures == [("task-1", "cancel_dispatch_deferred")]


def test_retry_creates_a_distinct_task_lineage() -> None:
    store, queue = StoreFake(), QueueFake()
    retry = SubmitTaskCommand(
        "task-2",
        "trace-2",
        "command-2",
        "flow.generate",
        retry_of_task_public_id="task-1",
    )
    TaskSubmissionService(store, queue).submit(retry)
    assert store.created[0].task_public_id == "task-2"
    assert store.created[0].retry_of_task_public_id == "task-1"
    assert queue.enqueued == [("task-2", "trace-2")]
