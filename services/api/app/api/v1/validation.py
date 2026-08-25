from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Query, Request

from app.modules.sprint1.service import Sprint1Service
from app.modules.validation.service import service
from app.platform.errors import ApiError

router = APIRouter(include_in_schema=False)
auth_service = Sprint1Service()


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


def _user(authorization: str | None) -> int:
    return int(auth_service.authenticate(authorization)["id"])


def _path_id(value: str, field: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ApiError("VALIDATION_ERROR", f"{field} must be a positive ID", 422)
    return value


def _key(value: str | None) -> str:
    if value is None or not 8 <= len(value) <= 128:
        raise ApiError("VALIDATION_ERROR", "Idempotency-Key must contain 8 to 128 characters", 422)
    return value


@router.post("/api/v1/test-records/{id}:conclude-no-issue")
def conclude_no_issue(
    id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.conclude_no_issue(
            record_id=_path_id(id, "id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.get("/api/v1/project-versions/{version_id}/issues")
def list_issues(
    version_id: str,
    request: Request,
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.list_issues(
            version_id=_path_id(version_id, "version_id"),
            user_id=_user(authorization),
            cursor=cursor,
            page_size=page_size,
        ),
    )


@router.post("/api/v1/project-versions/{version_id}/issues", status_code=201)
def create_issue(
    version_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.create_issue(
            version_id=_path_id(version_id, "version_id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.get("/api/v1/issues/{issue_id}")
def get_issue(
    issue_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.get_issue(issue_id=_path_id(issue_id, "issue_id"), user_id=_user(authorization)),
    )


@router.patch("/api/v1/issues/{issue_id}")
def update_issue(
    issue_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.update_issue(
            issue_id=_path_id(issue_id, "issue_id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )


@router.post("/api/v1/issues/{issue_id}/dispositions")
def create_disposition(
    issue_id: str,
    request: Request,
    body: Annotated[dict[str, Any], Body()],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    return _ok(
        request,
        service.create_disposition(
            issue_id=_path_id(issue_id, "issue_id"),
            user_id=_user(authorization),
            payload=body,
            key=_key(idempotency_key),
            trace_id=request.state.trace_id,
        ),
    )
