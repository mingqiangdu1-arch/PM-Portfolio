from __future__ import annotations

from dataclasses import dataclass

from app.tasking.ports import DurableTaskStore, SubmitTaskCommand, TaskQueue


class NewTaskRejected(RuntimeError):
    reason_code = "broker_unavailable"


class TaskDispatchFailed(RuntimeError):
    reason_code = "dispatch_failed_after_durable_create"


@dataclass(frozen=True, slots=True)
class CancellationOutcome:
    status: str
    dispatch_deferred: bool


class TaskSubmissionService:
    """Coordinates durable facts with Celery dispatch without using Redis as truth."""

    def __init__(self, store: DurableTaskStore, queue: TaskQueue) -> None:
        self._store = store
        self._queue = queue

    def submit(self, command: SubmitTaskCommand) -> str:
        try:
            self._queue.ensure_available()
        except Exception as exc:
            raise NewTaskRejected(self.reason(exc)) from exc

        self._store.create_queued_task(command)
        try:
            self._queue.enqueue(command.task_public_id, command.trace_id)
        except Exception as exc:
            self._store.record_dispatch_failure(
                command.task_public_id,
                TaskDispatchFailed.reason_code,
            )
            raise TaskDispatchFailed(self.reason(exc)) from exc
        return "queued"

    def cancel(self, task_public_id: str, trace_id: str, command_id: str) -> CancellationOutcome:
        self._store.request_cancel(task_public_id, command_id)
        try:
            self._queue.request_cancel(task_public_id, trace_id)
        except Exception:
            self._store.record_cancel_dispatch_failure(task_public_id, "cancel_dispatch_deferred")
            return CancellationOutcome(status="cancel_requested", dispatch_deferred=True)
        return CancellationOutcome(status="cancel_requested", dispatch_deferred=False)

    @staticmethod
    def reason(exc: Exception) -> str:
        return exc.__class__.__name__.lower()
