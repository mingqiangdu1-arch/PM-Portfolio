from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Request

from app.modules.confirmation.service import service
from app.modules.sprint1.service import Sprint1Service
from app.platform.errors import ApiError

router = APIRouter(include_in_schema=False)
auth_service = Sprint1Service()


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


def _key(value: str | None) -> str:
    if value is None or not 8 <= len(value) <= 128:
        raise ApiError("VALIDATION_ERROR", "Idempotency-Key must contain 8 to 128 characters", 422)
    return value


def _user(authorization: str | None) -> int:
    return int(auth_service.authenticate(authorization)["id"])


def _path_id(value: str, field: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a positive ID", 422)
    return value


def _body_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a positive string ID", 422)
    return value


@router.get("/api/v1/project-versions/{version_id}/implementation-plans")
def list_plans(
    version_id: str, request: Request, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    return _ok(
        request,
        service.list_plans(
            version_id=_path_id(version_id, "version_id"), user_id=_user(authorization)
        ),
    )


@router.post("/api/v1/project-versions/{version_id}/implementation-plans", status_code=201)
def create_plan(
    version_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    user_id = _user(authorization)
    _body_id(body.get("source_prd_version_id"), "source_prd_version_id")
    _body_id(body.get("source_design_review_id"), "source_design_review_id")
    return _ok(
        request,
        service.create_plan(
            version_id=_path_id(version_id, "version_id"),
            user_id=user_id,
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.get("/api/v1/implementation-plans/{plan_id}")
def get_plan(
    plan_id: str, request: Request, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    return _ok(
        request, service.get_plan(plan_id=_path_id(plan_id, "id"), user_id=_user(authorization))
    )


@router.post("/api/v1/implementation-plans/{plan_id}/versions", status_code=201)
def create_plan_version(
    plan_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.create_plan_version(
            plan_id=_path_id(plan_id, "id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.post("/api/v1/plan-versions/{version_id}:set-effective")
def set_effective(
    version_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.set_effective(
            version_id=_path_id(version_id, "id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.get("/api/v1/implementation-plans/{plan_id}/confirmation-rounds")
def list_rounds(
    plan_id: str, request: Request, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    return _ok(
        request, service.list_rounds(plan_id=_path_id(plan_id, "id"), user_id=_user(authorization))
    )


@router.post("/api/v1/implementation-plans/{plan_id}/confirmation-rounds", status_code=201)
def create_round(
    plan_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    user_id = _user(authorization)
    _body_id(body.get("plan_version_id"), "plan_version_id")
    return _ok(
        request,
        service.create_round(
            plan_id=_path_id(plan_id, "id"),
            user_id=user_id,
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.get("/api/v1/confirmation-rounds/{round_id}")
def get_round(
    round_id: str, request: Request, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    return _ok(
        request, service.get_round(round_id=_path_id(round_id, "id"), user_id=_user(authorization))
    )


@router.patch("/api/v1/confirmation-rounds/{round_id}")
def update_round(
    round_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    user_id = _user(authorization)
    if idempotency_key is not None:
        raise ApiError("VALIDATION_ERROR", "PATCH does not accept Idempotency-Key", 422)
    _body_id(body.get("plan_version_id"), "plan_version_id")
    return _ok(
        request,
        service.update_round(
            round_id=_path_id(round_id, "id"),
            user_id=user_id,
            payload=body,
            trace_id=request.state.trace_id,
            idempotency_key=idempotency_key,
        ),
    )


@router.post("/api/v1/confirmation-rounds/{round_id}:confirm")
def confirm_round(
    round_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.confirm_round(
            round_id=_path_id(round_id, "id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )
