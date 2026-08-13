from __future__ import annotations

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.api.tasks import configure_task_dependencies
from app.tasking.redis_celery import RedisCeleryQueue
from app.tasking.repository import MySQLTaskRepository
from app.workers.celery_app import celery_app
from app.workers.tasks import configure_runtime
from app.workers.runtime import TaskRuntime
from app.context.runtime import BusinessContextClient
from app.security import ServiceJwtIssuer
from app.requirement_clarification.formal_mock import FormalMockRequirementClarifier
from app.integrations.result_storage import S3ResultObjectStore
import redis
from urllib.parse import unquote, urlparse


def create_app() -> FastAPI:
    settings = Settings.from_env()
    configure_runtime(None)
    configure_logging()
    application = FastAPI(
        title="AI Product Validation Internal Service",
        version="0.1.3",
        docs_url="/internal/docs" if settings.environment in {"local", "ci"} else None,
        redoc_url=None,
    )
    application.include_router(health_router)
    application.include_router(tasks_router)
    queue = RedisCeleryQueue(redis.Redis.from_url(settings.broker_url), celery_app, queue_name=settings.task_default_queue)
    repository = None
    if settings.ai_database_url:
        import pymysql
        parsed = urlparse(settings.ai_database_url)
        if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path:
            raise ValueError("AI_DATABASE_URL must be a mysql URL")
        repository = MySQLTaskRepository(lambda: pymysql.connect(host=parsed.hostname, port=parsed.port or 3306, user=unquote(parsed.username or ""), password=unquote(parsed.password or ""), database=unquote(parsed.path.lstrip("/")), cursorclass=pymysql.cursors.DictCursor, autocommit=False))
    configure_task_dependencies(repository=repository, queue=queue)
    if repository is not None and settings.ai_result_storage_endpoint and settings.ai_result_storage_bucket and settings.business_api_url and settings.business_api_jwt_secret:
        import boto3
        issuer = ServiceJwtIssuer(secret=settings.business_api_jwt_secret, issuer="ai-worker", subject="ai-worker", audience="business-api", ttl_seconds=settings.service_jwt_ttl_seconds)
        context_client = BusinessContextClient(base_url=settings.business_api_url, token=lambda task_id, trace: issuer.issue(scopes={"context:read"}, task_id=task_id, trace_id=trace))
        storage_client = boto3.client("s3", endpoint_url=settings.ai_result_storage_endpoint, region_name=settings.ai_result_storage_region, aws_access_key_id=settings.ai_result_storage_access_key, aws_secret_access_key=settings.ai_result_storage_secret_key)
        configure_runtime(TaskRuntime(repository=repository, context_client=context_client, provider=FormalMockRequirementClarifier(), token_budget=settings.context_token_budget, object_store=S3ResultObjectStore(storage_client, bucket=settings.ai_result_storage_bucket, prefix=settings.ai_result_storage_prefix)))
    return application


app = create_app()
