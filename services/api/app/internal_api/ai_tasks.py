from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request

from app.modules.ai_tasks.service import ContextService
from app.platform.errors import ApiError

router = APIRouter(include_in_schema=False)
service = ContextService()


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


@router.post("/internal/v1/ai/tasks/{task_id}/context-snapshot")
def context_snapshot(task_id: str, request: Request, body: Annotated[dict[str, Any], Body()], authorization: Annotated[str | None, Header()] = None, x_trace_id: Annotated[str | None, Header(alias="X-Trace-ID")] = None, x_task_public_id: Annotated[str | None, Header(alias="X-Task-Public-ID")] = None) -> dict[str, Any]:
    if x_task_public_id is not None and x_task_public_id != task_id:
        raise ApiError(code="SERVICE_TOKEN_INVALID", message="Task header binding is invalid", http_status=401)
    return service.context_snapshot(task_id=task_id, authorization=authorization, body=body, trace_id=x_trace_id)


@router.post("/internal/v1/ai/tasks/{task_id}/target-freshness")
def target_freshness(task_id: str, request: Request, body: Annotated[dict[str, Any], Body()], authorization: Annotated[str | None, Header()] = None, x_trace_id: Annotated[str | None, Header(alias="X-Trace-ID")] = None, x_task_public_id: Annotated[str | None, Header(alias="X-Task-Public-ID")] = None) -> dict[str, Any]:
    if x_task_public_id is not None and x_task_public_id != task_id:
        raise ApiError(code="SERVICE_TOKEN_INVALID", message="Task header binding is invalid", http_status=401)
    return service.freshness(task_id=task_id, authorization=authorization, trace_id=x_trace_id, body=body)
