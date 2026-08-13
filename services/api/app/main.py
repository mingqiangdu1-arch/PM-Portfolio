from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.platform.config import get_settings
from app.platform.errors import install_exception_handlers
from app.platform.logging import configure_logging
from app.platform.openapi import configure_openapi
from app.platform.trace import TraceMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title="AI Product Design and Validation API",
        summary="Sprint 2 Requirement/Baseline R4 implementation candidate",
        description=(
            "Sprint 2 Requirement/Baseline R4 implementation candidate authorized by "
            "PORTFOLIO-P1-RUNTIME-01. It remains pending Review and the shared real-runtime "
            "Gate; persistence adapters and FLOW remain disabled."
        ),
        version=settings.app_release,
        openapi_version="3.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
    )
    application.add_middleware(TraceMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-CSRF-Token"],
    )
    application.include_router(api_router)
    install_exception_handlers(application)
    configure_openapi(application)
    return application


app = create_app()
