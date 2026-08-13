from __future__ import annotations

from typing import Any


class RedisCeleryQueue:
    """Redis readiness plus ID-only Celery dispatch adapter."""

    def __init__(self, redis_client: Any, celery: Any, *, queue_name: str) -> None:
        self._redis = redis_client
        self._celery = celery
        self._queue_name = queue_name

    def ensure_available(self) -> None:
        if self._redis.ping() is not True:
            raise ConnectionError("Redis ping did not return true")

    def enqueue(self, task_public_id: str, trace_id: str) -> None:
        self._celery.send_task(
            "ai.execute_task",
            kwargs={"task_public_id": task_public_id, "trace_id": trace_id},
            queue=self._queue_name,
        )

    def request_cancel(self, task_public_id: str, trace_id: str) -> None:
        self._celery.send_task(
            "ai.request_cancel",
            kwargs={"task_public_id": task_public_id, "trace_id": trace_id},
            queue=self._queue_name,
        )
