from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
import redis

from app.core.config import Settings
from app.integrations import BusinessApiHealthClient, DependencyHealth
from app.security import ServiceJwtError, ServiceJwtIssuer, ServiceJwtVerifier, ServicePrincipal


router = APIRouter(prefix="/internal/v1/ai/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive", "service": "ai-api"}


def require_health_scope(authorization: str | None = Header(default=None)) -> ServicePrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SERVICE_TOKEN_REQUIRED",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = Settings.from_env()
    if not settings.internal_jwt_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SERVICE_AUTH_NOT_CONFIGURED")
    verifier = ServiceJwtVerifier(
        secret=settings.internal_jwt_secret,
        audience="ai-api",
        allowed_issuers={"business-api", "monitoring"},
    )
    try:
        return verifier.verify(authorization.removeprefix("Bearer "), required_scopes={"health"})
    except ServiceJwtError as exc:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        raise HTTPException(status_code=exc.status_code, detail=exc.code, headers=headers) from exc


@router.get("/ready")
def ready(
    response: Response,
    principal: ServicePrincipal = Depends(require_health_scope),
    x_trace_id: str | None = Header(default=None),
) -> dict[str, object]:
    settings = Settings.from_env()
    broker_available = probe_broker(settings.broker_url)
    business_api = probe_business_api(settings, trace_id=x_trace_id or principal.trace_id or principal.jwt_id)
    if not broker_available or business_api.status not in {"available", "not_required"}:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness_payload(settings, broker_available=broker_available, business_api=business_api)


def readiness_payload(
    settings: Settings,
    *,
    broker_available: bool,
    business_api: DependencyHealth | None = None,
) -> dict[str, object]:
    business_api = business_api or DependencyHealth("not_required")
    accepting_new_tasks = broker_available and business_api.status in {"available", "not_required"}
    return {
        "status": "ready" if accepting_new_tasks else "dependency_unavailable",
        "accepting_new_tasks": accepting_new_tasks,
        "capabilities": {"ai_tasks": "ready" if accepting_new_tasks else "unavailable"},
        "dependencies": {
            "provider": settings.provider_mode,
            "context": settings.context_mode,
            "broker": "available" if broker_available else "unavailable",
            "business_api": business_api.status,
        },
        "flow_enabled": settings.flow_enabled,
        "wave": 2,
    }


def probe_business_api(settings: Settings, *, trace_id: str) -> DependencyHealth:
    if settings.context_mode != "business_api":
        return DependencyHealth("not_required")
    if not settings.business_api_url or not settings.business_api_jwt_secret:
        return DependencyHealth("unavailable", error_class="configuration")
    issuer = ServiceJwtIssuer(
        secret=settings.business_api_jwt_secret,
        issuer="ai-api",
        subject="ai-api",
        audience="business-api",
        ttl_seconds=settings.service_jwt_ttl_seconds,
    )
    return BusinessApiHealthClient(base_url=settings.business_api_url, token_issuer=issuer).probe(trace_id=trace_id)


def probe_broker(broker_url: str) -> bool:
    client = redis.Redis.from_url(
        broker_url,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        return client.ping() is True
    except redis.RedisError:
        return False
    finally:
        client.close()
