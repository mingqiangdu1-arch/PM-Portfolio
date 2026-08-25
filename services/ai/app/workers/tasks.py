"""Celery task entry points; durable state remains outside Redis."""

from app.workers.celery_app import celery_app

_runtime = None

def configure_runtime(runtime) -> None:
    global _runtime
    _runtime = runtime

def runtime() -> object:
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime_from_env()
    return _runtime


def _build_runtime_from_env() -> object:
    """Worker-side production assembly; Celery does not import FastAPI ``main``."""
    from urllib.parse import unquote, urlparse
    from app.core.config import Settings
    from app.tasking.repository import MySQLTaskRepository
    from app.context.runtime import BusinessContextClient
    from app.security import ServiceJwtIssuer
    from app.requirement_clarification.formal_mock import FormalMockRequirementClarifier
    from app.requirement_clarification.real_provider import RealRequirementClarifier
    from app.providers.openai_compatible import OpenAICompatibleAdapter
    from app.providers.profiles.deepseek import deepseek_profile
    from app.integrations.result_storage import S3ResultObjectStore
    from app.workers.runtime import TaskRuntime
    settings = Settings.from_env()
    if not (settings.ai_database_url and settings.ai_result_storage_endpoint and settings.ai_result_storage_bucket and settings.business_api_url and settings.business_api_jwt_secret):
        raise RuntimeError("AI production runtime dependencies are not configured")
    import pymysql
    parsed = urlparse(settings.ai_database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path:
        raise RuntimeError("AI_DATABASE_URL must be a mysql URL")
    repository = MySQLTaskRepository(lambda: pymysql.connect(host=parsed.hostname, port=parsed.port or 3306, user=unquote(parsed.username or ""), password=unquote(parsed.password or ""), database=unquote(parsed.path.lstrip("/")), cursorclass=pymysql.cursors.DictCursor, autocommit=False))
    issuer = ServiceJwtIssuer(secret=settings.business_api_jwt_secret, issuer="ai-worker", subject="ai-worker", audience="business-api", ttl_seconds=settings.service_jwt_ttl_seconds)
    context_client = BusinessContextClient(base_url=settings.business_api_url, token=lambda task_id, trace: issuer.issue(scopes={"context:read"}, task_id=task_id, trace_id=trace))
    import boto3
    client = boto3.client("s3", endpoint_url=settings.ai_result_storage_endpoint, region_name=settings.ai_result_storage_region, aws_access_key_id=settings.ai_result_storage_access_key, aws_secret_access_key=settings.ai_result_storage_secret_key)
    if settings.provider_mode == "openai_compatible":
        if not settings.provider_api_key:
            raise RuntimeError("DeepSeek API key is not configured")
        adapter = OpenAICompatibleAdapter(
            deepseek_profile(),
            api_key=settings.provider_api_key,
            network_authorized=settings.live_provider_authorized,
        )
        provider = RealRequirementClarifier(adapter, model=settings.provider_model)
    else:
        provider = FormalMockRequirementClarifier()
    return TaskRuntime(repository=repository, context_client=context_client, provider=provider, token_budget=settings.context_token_budget, object_store=S3ResultObjectStore(client, bucket=settings.ai_result_storage_bucket, prefix=settings.ai_result_storage_prefix))


@celery_app.task(name="ai.execute_task", ignore_result=True)
def execute_task(*, task_public_id: str, trace_id: str) -> None:
    if not task_public_id or not trace_id:
        raise ValueError("task_public_id and trace_id are required")
    runtime().execute(task_public_id=task_public_id, trace_id=trace_id)


@celery_app.task(name="ai.request_cancel", ignore_result=True)
def request_cancel(*, task_public_id: str, trace_id: str) -> None:
    if not task_public_id or not trace_id:
        raise ValueError("task_public_id and trace_id are required")
    # Cooperative cancellation reads durable cancel_requested state. A revoke
    # flag in Redis is never the only cancellation fact.
