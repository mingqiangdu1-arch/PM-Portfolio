from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SubmitTaskCommand:
    task_public_id: str
    trace_id: str
    command_id: str
    task_type: str
    retry_of_task_public_id: str | None = None


class DurableTaskStore(Protocol):
    """Port owned by the business API and its MySQL transaction."""

    def create_queued_task(self, command: SubmitTaskCommand) -> None: ...

    def record_dispatch_failure(self, task_public_id: str, reason_code: str) -> None: ...

    def request_cancel(self, task_public_id: str, command_id: str) -> None: ...

    def record_cancel_dispatch_failure(self, task_public_id: str, reason_code: str) -> None: ...


class TaskQueue(Protocol):
    def ensure_available(self) -> None: ...

    def enqueue(self, task_public_id: str, trace_id: str) -> None: ...

    def request_cancel(self, task_public_id: str, trace_id: str) -> None: ...
