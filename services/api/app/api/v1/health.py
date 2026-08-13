from fastapi import APIRouter, Request, status

from app.platform.config import get_settings
from app.platform.schemas import ApiResponse, HealthData

router = APIRouter(tags=["health"])


def _health_response(request: Request, state: str) -> ApiResponse[HealthData]:
    settings = get_settings()
    return ApiResponse(
        code="OK",
        message="success",
        data=HealthData(
            status=state,
            service=settings.app_name,
            release=settings.app_release,
            environment=settings.app_env,
        ),
        trace_id=request.state.trace_id,
    )


@router.get(
    "/health/live",
    response_model=ApiResponse[HealthData],
    operation_id="getLiveness",
)
async def liveness(request: Request) -> ApiResponse[HealthData]:
    return _health_response(request, "live")


@router.get(
    "/health/ready",
    response_model=ApiResponse[HealthData],
    operation_id="getReadiness",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Dependency unavailable"}},
)
async def readiness(request: Request) -> ApiResponse[HealthData]:
    # Sprint 0 verifies process readiness. Database, Redis and object-storage probes
    # are registered by their infrastructure adapters when those adapters are enabled.
    return _health_response(request, "ready")


@router.get(
    "/api/v1/health",
    response_model=ApiResponse[HealthData],
    operation_id="getApiHealth",
)
async def api_health(request: Request) -> ApiResponse[HealthData]:
    return _health_response(request, "ready")
