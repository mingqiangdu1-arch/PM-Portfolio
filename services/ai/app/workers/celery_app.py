from __future__ import annotations

from celery import Celery

from app.core.config import Settings


settings = Settings.from_env()
celery_app = Celery(
    "ai_worker",
    broker=settings.broker_url,
    backend=None,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_default_queue=settings.task_default_queue,
    task_routes={
        "ai.execute_task": {"queue": settings.task_default_queue},
        "ai.request_cancel": {"queue": settings.task_default_queue},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="ai.worker.probe", ignore_result=True)
def worker_probe(task_public_id: str, trace_id: str) -> None:
    """Connectivity probe only; it does not create or mutate authoritative facts."""
    if not task_public_id or not trace_id:
        raise ValueError("task_public_id and trace_id are required")
