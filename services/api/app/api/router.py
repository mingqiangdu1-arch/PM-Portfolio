from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.requirements import router as requirements_router
from app.api.v1.prds import router as prds_router
from app.api.v1.ai_tasks import router as ai_tasks_router
from app.api.v1.sprint1 import router as sprint1_router
from app.internal_api.health import router as internal_health_router
from app.internal_api.ai_tasks import router as internal_ai_tasks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(sprint1_router)
api_router.include_router(requirements_router)
api_router.include_router(prds_router)
api_router.include_router(ai_tasks_router)
api_router.include_router(internal_health_router)
api_router.include_router(internal_ai_tasks_router)
