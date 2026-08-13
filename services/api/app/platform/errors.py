from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status
from starlette.exceptions import HTTPException as StarletteHttpException

from app.platform.schemas import ErrorResponse, FieldError


@dataclass(slots=True)
class ApiError(Exception):
    code: str
    message: str
    http_status: int = status.HTTP_400_BAD_REQUEST
    details: list[dict[str, Any]] | None = None


def _response(request: Request, error: ApiError) -> JSONResponse:
    body = ErrorResponse(
        code=error.code,
        message=error.message,
        details=[FieldError.model_validate(item) for item in (error.details or [])],
        trace_id=request.state.trace_id,
    )
    return JSONResponse(status_code=error.http_status, content=body.model_dump(mode="json"))


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _response(request, exc)

    @app.exception_handler(StarletteHttpException)
    async def http_error_handler(
        request: Request, exc: StarletteHttpException
    ) -> JSONResponse:
        code_by_status = {
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_409_CONFLICT: "VERSION_CONFLICT",
        }
        return _response(
            request,
            ApiError(
                code=code_by_status.get(exc.status_code, "HTTP_ERROR"),
                message=str(exc.detail),
                http_status=exc.status_code,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "reason": item["msg"],
            }
            for item in exc.errors()
        ]
        return _response(
            request,
            ApiError(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details=details,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return _response(
            request,
            ApiError(
                code="INTERNAL_ERROR",
                message="Internal server error",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ),
        )
