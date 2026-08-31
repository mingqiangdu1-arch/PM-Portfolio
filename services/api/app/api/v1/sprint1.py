from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Cookie, Depends, Header, Query, Request, Response

from app.modules.sprint1.service import Sprint1Service
from app.platform.config import get_settings
from app.platform.errors import ApiError
from app.platform.http import require_idempotency_key


router = APIRouter(include_in_schema=False)
service = Sprint1Service()


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


def _user(authorization: str | None) -> dict[str, Any]:
    return service.authenticate(authorization)


def _cookie_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if not origin and not referer:
        raise ApiError(code="ORIGIN_REQUIRED", message="Origin or Referer is required", http_status=403)
    actual = origin
    if not actual and referer:
        parsed = urlsplit(referer)
        actual = f"{parsed.scheme}://{parsed.netloc}"
    if actual not in get_settings().cors_allowed_origins:
        raise ApiError(code="ORIGIN_MISMATCH", message="Cookie command must be same-origin", http_status=403)


def _set_refresh(response: Response, value: str) -> None:
    response.set_cookie(
        "refresh_token",
        value,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=get_settings().app_env in {"staging", "production"},
        samesite="strict",
        path="/api/v1/auth",
    )


def _clear_refresh(response: Response) -> None:
    response.delete_cookie("refresh_token", path="/api/v1/auth", httponly=True, samesite="strict")


@router.post("/api/v1/auth/register")
def register(request: Request, response: Response, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    data, refresh = service.register(
        email=body["email"], password=body["password"], display_name=body["display_name"],
        trace_id=request.state.trace_id,
    )
    _set_refresh(response, refresh)
    return _ok(request, data)


@router.post("/api/v1/auth/login")
def login(request: Request, response: Response, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    data, refresh = service.login(email=body["email"], password=body["password"], trace_id=request.state.trace_id)
    _set_refresh(response, refresh)
    return _ok(request, data)


@router.post("/api/v1/auth/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    _cookie_origin(request)
    if not refresh_token:
        raise ApiError(code="REFRESH_INVALID", message="Refresh token is missing", http_status=401)
    data, rotated = service.refresh(cookie=refresh_token, trace_id=request.state.trace_id)
    _set_refresh(response, rotated)
    return _ok(request, data)


@router.post("/api/v1/auth/logout")
def logout(
    request: Request,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    _cookie_origin(request)
    user = service.authenticate(authorization) if authorization else service.authenticate_refresh_cookie(refresh_token)
    service.logout(user=user, trace_id=request.state.trace_id)
    _clear_refresh(response)
    return _ok(request, {"logged_out": True})


@router.get("/api/v1/session")
def session(request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, {"user": {"id": str(user["id"]), "email": user["email"], "display_name": user["display_name"], "system_roles": ["admin"] if user["system_role"] == "admin" else [], "status": user["status"]}, "system_roles": ["admin"] if user["system_role"] == "admin" else [], "session_id": user["session_public_id"], "expires_at": user["session_expires_at"].replace(tzinfo=None).isoformat() + "Z"})


@router.get("/api/v1/projects")
def list_projects(request: Request, authorization: Annotated[str | None, Header()] = None, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.list_projects(user_id=user["id"], limit=limit))


@router.post("/api/v1/projects")
def create_project(request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.create_project(user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/projects/{project_id}")
def get_project(project_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.get_project(project_id=project_id, user_id=user["id"]))


@router.patch("/api/v1/projects/{project_id}")
def update_project(project_id: int, request: Request, body: Annotated[dict[str, Any], Body()], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.update_project(project_id=project_id, user_id=user["id"], payload=body, trace_id=request.state.trace_id))


@router.post("/api/v1/projects/{project_id}:archive")
def archive_project(project_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.project_lifecycle(project_id=project_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id, restore=False))


@router.post("/api/v1/projects/{project_id}:restore")
def restore_project(project_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.project_lifecycle(project_id=project_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id, restore=True))


@router.get("/api/v1/projects/{project_id}/members")
def list_members(project_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.list_members(project_id=project_id, user_id=user["id"]))


@router.put("/api/v1/projects/{project_id}/members/{target_user_id}")
def put_member(project_id: int, target_user_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.put_member(project_id=project_id, target_user_id=target_user_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/projects/{project_id}/versions")
def list_versions(project_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.list_versions(project_id=project_id, user_id=user["id"]))


@router.get("/api/v1/project-versions/{version_id}")
def get_version(version_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.get_version(version_id=version_id, user_id=user["id"]))


@router.get("/api/v1/project-versions/{left_id}:compare")
def compare_versions(left_id: int, request: Request, right_version_id: int, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.compare_versions(left_id=left_id, right_id=right_version_id, user_id=user["id"]))


@router.post("/api/v1/projects/{project_id}/versions/{version_id}:set-working")
def set_working(project_id: int, version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.set_working(project_id=project_id, version_id=version_id, user_id=user["id"], expected=body["expected_project_version"], reason=body["reason"], key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/projects/{project_id}/versions:derive")
def derive_version(project_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.derive_version(project_id=project_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/projects/{project_id}/context")
def get_context(project_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.get_context(project_id=project_id, user_id=user["id"]))


@router.patch("/api/v1/projects/{project_id}/context")
def update_context(project_id: int, request: Request, body: Annotated[dict[str, Any], Body()], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.update_context(project_id=project_id, user_id=user["id"], payload=body, trace_id=request.state.trace_id))


@router.post("/api/v1/files/uploads")
def init_upload(request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.init_upload(user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/files/uploads/{upload_id}:complete")
def complete_upload(upload_id: str, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.complete_upload(upload_id=upload_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/files/uploads/{upload_id}:abort")
def abort_upload(upload_id: str, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.abort_upload(upload_id=upload_id, user_id=user["id"], reason=body["reason"], key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/files/{file_id}")
def get_file(file_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.get_file(file_id=file_id, user_id=user["id"]))


@router.get("/api/v1/projects/{project_id}/files")
def list_project_files(project_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.list_project_files(project_id=project_id, user_id=user["id"]))


@router.get("/api/v1/files/{file_id}/versions")
def list_file_versions(file_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.list_file_versions(file_id=file_id, user_id=user["id"]))


@router.post("/api/v1/file-versions/{version_id}:download")
def download_file(version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.download(version_id=version_id, user_id=user["id"], disposition=body["disposition"], trace_id=request.state.trace_id))


@router.post("/api/v1/file-versions/{version_id}/relations")
def create_relation(version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.create_relation(version_id=version_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/files/{file_id}:archive")
def archive_file(file_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, require_idempotency_key], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = _user(authorization)
    return _ok(request, service.archive_file(file_id=file_id, user_id=user["id"], payload=body, key=key, trace_id=request.state.trace_id))
