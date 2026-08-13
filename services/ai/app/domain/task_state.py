from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    PRECHECKING = "prechecking"
    BLOCKED = "blocked"
    QUEUED = "queued"
    PREPARING = "preparing"
    GENERATING = "generating"
    CHECKING = "checking"
    READY = "ready"
    PARTIAL_RESULT = "partial_result"
    QUALITY_BLOCKED = "quality_blocked"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"
    STALE_TARGET = "stale_target"


TERMINAL_STATUSES = {
    TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.EXPIRED, TaskStatus.STALE_TARGET,
}

ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PRECHECKING: frozenset({TaskStatus.BLOCKED, TaskStatus.QUEUED, TaskStatus.FAILED}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.PRECHECKING, TaskStatus.CANCELLED}),
    TaskStatus.QUEUED: frozenset({TaskStatus.PREPARING, TaskStatus.CANCEL_REQUESTED, TaskStatus.FAILED, TaskStatus.EXPIRED}),
    TaskStatus.PREPARING: frozenset({TaskStatus.GENERATING, TaskStatus.CANCEL_REQUESTED, TaskStatus.FAILED, TaskStatus.STALE_TARGET}),
    TaskStatus.GENERATING: frozenset({TaskStatus.CHECKING, TaskStatus.CANCEL_REQUESTED, TaskStatus.FAILED, TaskStatus.STALE_TARGET}),
    TaskStatus.CHECKING: frozenset({TaskStatus.READY, TaskStatus.PARTIAL_RESULT, TaskStatus.QUALITY_BLOCKED, TaskStatus.CANCEL_REQUESTED, TaskStatus.FAILED, TaskStatus.STALE_TARGET}),
    TaskStatus.QUALITY_BLOCKED: frozenset({TaskStatus.CHECKING, TaskStatus.EXPIRED, TaskStatus.STALE_TARGET}),
    TaskStatus.READY: frozenset({TaskStatus.EXPIRED, TaskStatus.STALE_TARGET}),
    TaskStatus.PARTIAL_RESULT: frozenset({TaskStatus.EXPIRED, TaskStatus.STALE_TARGET}),
    TaskStatus.CANCEL_REQUESTED: frozenset({TaskStatus.CANCELLED, TaskStatus.FAILED}),
    TaskStatus.CANCELLED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.EXPIRED: frozenset(),
    TaskStatus.STALE_TARGET: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Transition:
    source: TaskStatus
    target: TaskStatus


class InvalidTaskTransition(ValueError):
    pass


def transition(source: TaskStatus, target: TaskStatus) -> Transition:
    if target not in ALLOWED_TRANSITIONS[source]:
        raise InvalidTaskTransition(f"invalid AI task transition: {source} -> {target}")
    return Transition(source=source, target=target)
