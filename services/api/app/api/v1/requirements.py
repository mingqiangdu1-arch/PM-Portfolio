from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Request

from app.modules.ai_tasks.service import AiTaskService
from app.modules.requirements.service import RequirementService
from app.modules.sprint1.service import Sprint1Service
from app.platform.errors import ApiError


async def require_requirement_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if idempotency_key is None or not 8 <= len(idempotency_key) <= 128:
        raise ApiError(code="VALIDATION_ERROR", message="Idempotency-Key must contain 8 to 128 characters", http_status=422)
    return idempotency_key


router = APIRouter(include_in_schema=False)
service = RequirementService(ai_result_authority=AiTaskService())
auth_service = Sprint1Service()


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


@router.get("/api/v1/project-versions/{version_id}/requirements")
def list_requirements(
    version_id: int,
    request: Request,
    status: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(
        request,
        service.list_requirements(version_id=version_id, user_id=int(user["id"]), status=status),
    )


@router.post("/api/v1/project-versions/{version_id}/requirements")
def create_requirement(
    version_id: int,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    key: Annotated[str, Depends(require_requirement_idempotency_key)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.create_requirement(version_id=version_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/requirements/{requirement_id}")
def get_requirement(
    requirement_id: int,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.get_requirement(requirement_id=requirement_id, user_id=int(user["id"])))


@router.patch("/api/v1/requirement-versions/{version_id}")
def revise_requirement_version(
    version_id: int,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.revise(version_id=version_id, user_id=int(user["id"]), payload=body, trace_id=request.state.trace_id))


@router.post("/api/v1/requirement-versions/{version_id}:set-clarification-mode")
def set_clarification_mode(version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_requirement_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.set_clarification_mode(version_id=version_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/requirement-versions/{version_id}/clarification-answers")
def submit_clarification_answers(version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_requirement_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.submit_clarification_answers(version_id=version_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/requirement-versions/{version_id}:confirm")
def confirm_requirement_version(
    version_id: int,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    key: Annotated[str, Depends(require_requirement_idempotency_key)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(
        request,
        service.confirm(
            version_id=version_id,
            user_id=int(user["id"]),
            payload=body,
            key=key,
            trace_id=request.state.trace_id,
        ),
    )
