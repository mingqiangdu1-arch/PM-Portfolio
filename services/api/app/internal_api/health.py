from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Request

from app.platform.config import get_settings
from app.platform.errors import ApiError
from app.platform.security import decode_hs256


router = APIRouter(include_in_schema=False)


def require_health_service(authorization: str | None) -> dict[str, Any]:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer ") or not settings.internal_service_jwt_secret:
        raise ApiError(code="SERVICE_TOKEN_INVALID", message="Internal service authentication required", http_status=401)
    claims = decode_hs256(
        authorization[7:],
        settings.internal_service_jwt_secret,
        audience="business-api",
        require_jti=True,
        max_ttl_seconds=300,
        clock_skew_seconds=30,
    )
    if claims.get("iss") not in {"ai-api", "monitoring"}:
        raise ApiError(code="SERVICE_TOKEN_INVALID", message="Internal service issuer is not allowed", http_status=401)
    if claims.get("iss") == "ai-api" and claims.get("sub") != "ai-api":
        raise ApiError(code="SERVICE_TOKEN_INVALID", message="AI service subject is not allowed", http_status=401)
    if claims.get("iss") == "monitoring" and claims.get("sub") != "monitoring":
        raise ApiError(code="SERVICE_TOKEN_INVALID", message="Monitoring subject is not allowed", http_status=401)
    scopes = set(str(claims.get("scope", "")).split())
    if "health" not in scopes:
        raise ApiError(code="FORBIDDEN", message="Internal service scope is insufficient", http_status=403)
    return claims


@router.get("/internal/v1/health")
def internal_health(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    require_health_service(authorization)
    settings = get_settings()
    return {
        "code": "OK",
        "message": "success",
        "data": {"status": "ready", "service": settings.app_name, "release": settings.app_release},
        "trace_id": request.state.trace_id,
    }
