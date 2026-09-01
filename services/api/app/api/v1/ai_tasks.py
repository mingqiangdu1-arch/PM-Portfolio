from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Query, Request

from app.modules.ai_tasks.service import AiTaskService
from app.modules.sprint1.service import Sprint1Service
from app.platform.errors import ApiError

router = APIRouter(include_in_schema=False)
service = AiTaskService()
auth_service = Sprint1Service()


def _key(value: str | None) -> str:
    if value is None or not 8 <= len(value) <= 128:
        raise ApiError(code="VALIDATION_ERROR", message="Idempotency-Key must contain 8 to 128 characters", http_status=422)
    return value


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


@router.get("/api/v1/ai/tasks")
def list_ai_tasks(
    request: Request,
    project_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(
        request,
        service.list_tasks(
            user_id=int(user["id"]),
            project_id=project_id,
            status=status,
            cursor=cursor,
        ),
    )


@router.post("/api/v1/ai/tasks")
def create_ai_task(
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.create_task(user_id=int(user["id"]), payload=body, key=_key(idempotency_key), trace_id=request.state.trace_id))


@router.get("/api/v1/ai/tasks/{task_id}")
def get_ai_task(task_id: str, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.get_task(user_id=int(user["id"]), task_id=task_id))


@router.get("/api/v1/ai/results/{result_id}")
def get_ai_result(result_id: str, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.get_result(user_id=int(user["id"]), result_id=result_id))


@router.post("/api/v1/ai/results/{result_id}:formalize")
def formalize_ai_result(
    result_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.formalize(user_id=int(user["id"]), result_id=result_id, payload=body, key=_key(idempotency_key), trace_id=request.state.trace_id))
