from __future__ import annotations

from dataclasses import dataclass
import os


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str
    environment: str
    product_release: str
    broker_url: str
    task_default_queue: str
    provider_mode: str
    context_mode: str
    live_provider_authorized: bool
    flow_enabled: bool
    internal_jwt_secret: str | None
    business_api_jwt_secret: str | None
    business_api_url: str | None
    service_jwt_ttl_seconds: int
    context_token_budget: int
    ai_database_url: str | None
    ai_result_storage_endpoint: str | None
    ai_result_storage_bucket: str | None
    ai_result_storage_region: str | None
    ai_result_storage_access_key: str | None
    ai_result_storage_secret_key: str | None
    ai_result_storage_prefix: str

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("AI_ENVIRONMENT", "local").strip().lower()
        provider_mode = os.getenv("AI_PROVIDER_MODE", "stub").strip().lower()
        context_mode = os.getenv("AI_CONTEXT_MODE", "stub").strip().lower()
        if environment not in {"local", "ci", "staging", "production"}:
            raise ValueError("AI_ENVIRONMENT must be local, ci, staging, or production")
        if provider_mode not in {"stub", "openai_compatible"}:
            raise ValueError("AI_PROVIDER_MODE is unsupported")
        if context_mode not in {"stub", "business_api"}:
            raise ValueError("AI_CONTEXT_MODE is unsupported")
        if environment == "ci" and provider_mode != "stub":
            raise ValueError("CI must use Provider Stub")
        if environment == "production" and (provider_mode == "stub" or context_mode == "stub"):
            raise ValueError("production cannot start with Provider or Context stubs")
        service_jwt_ttl_seconds = int(os.getenv("AI_SERVICE_JWT_TTL_SECONDS", "120"))
        if not 1 <= service_jwt_ttl_seconds <= 300:
            raise ValueError("AI_SERVICE_JWT_TTL_SECONDS must be between 1 and 300")
        context_token_budget = int(os.getenv("AI_CONTEXT_TOKEN_BUDGET", "12000"))
        if not 1 <= context_token_budget <= 200000:
            raise ValueError("AI_CONTEXT_TOKEN_BUDGET must be between 1 and 200000")
        internal_jwt_secret = os.getenv("AI_INTERNAL_JWT_SECRET") or None
        business_api_jwt_secret = os.getenv("AI_BUSINESS_API_JWT_SECRET") or None
        business_api_url = (os.getenv("AI_BUSINESS_API_URL") or "").rstrip("/") or None
        if environment in {"staging", "production"} and not internal_jwt_secret:
            raise ValueError("AI_INTERNAL_JWT_SECRET is required outside local/ci")
        database_url = os.getenv("AI_DATABASE_URL") or None
        storage_endpoint = os.getenv("AI_RESULT_STORAGE_ENDPOINT") or None
        storage_bucket = os.getenv("AI_RESULT_STORAGE_BUCKET") or None
        storage_region = os.getenv("AI_RESULT_STORAGE_REGION") or None
        storage_access_key = os.getenv("AI_RESULT_STORAGE_ACCESS_KEY") or None
        storage_secret_key = os.getenv("AI_RESULT_STORAGE_SECRET_KEY") or None
        storage_prefix = os.getenv("AI_RESULT_STORAGE_PREFIX", "ai-results/").strip("/") + "/"
        if not storage_prefix.startswith("ai-results/"):
            raise ValueError("AI_RESULT_STORAGE_PREFIX must stay under ai-results/")
        if environment in {"staging", "production"} and not all(
            (database_url, storage_endpoint, storage_bucket, storage_region, storage_access_key, storage_secret_key, business_api_url, business_api_jwt_secret)
        ):
            raise ValueError("AI database, result storage, and Business API configuration is required outside local/ci")
        return cls(
            service_name="ai-api",
            environment=environment,
            product_release=os.getenv("PRODUCT_RELEASE", "dev"),
            broker_url=os.getenv("AI_BROKER_URL", "redis://redis:6379/0"),
            task_default_queue=os.getenv("AI_TASK_DEFAULT_QUEUE", "interactive"),
            provider_mode=provider_mode,
            context_mode=context_mode,
            live_provider_authorized=_as_bool(
                os.getenv("AI_LIVE_PROVIDER_AUTHORIZED"),
                default=False,
            ),
            flow_enabled=_as_bool(os.getenv("FLOW_ENABLED"), default=False),
            internal_jwt_secret=internal_jwt_secret,
            business_api_jwt_secret=business_api_jwt_secret,
            business_api_url=business_api_url,
            service_jwt_ttl_seconds=service_jwt_ttl_seconds,
            context_token_budget=context_token_budget,
            ai_database_url=database_url,
            ai_result_storage_endpoint=storage_endpoint,
            ai_result_storage_bucket=storage_bucket,
            ai_result_storage_region=storage_region,
            ai_result_storage_access_key=storage_access_key,
            ai_result_storage_secret_key=storage_secret_key,
            ai_result_storage_prefix=storage_prefix,
        )

    def public_summary(self) -> dict[str, str | bool]:
        return {
            "service": self.service_name,
            "environment": self.environment,
            "product_release": self.product_release,
            "provider_mode": self.provider_mode,
            "context_mode": self.context_mode,
            "live_provider_authorized": self.live_provider_authorized,
            "flow_enabled": self.flow_enabled,
            "result_storage_configured": bool(self.ai_result_storage_endpoint and self.ai_result_storage_bucket),
        }
