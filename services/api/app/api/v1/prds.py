from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Request

from app.api.v1.requirements import require_requirement_idempotency_key
from app.modules.prds.service import PrdService
from app.modules.sprint1.service import Sprint1Service


router = APIRouter(include_in_schema=False)
service = PrdService()
auth_service = Sprint1Service()


def _ok(request: Request, data: Any) -> dict[str, Any]:
    return {"code": "OK", "message": "success", "data": data, "trace_id": request.state.trace_id}


@router.get("/api/v1/project-versions/{version_id}/prds")
def list_prds(version_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.list_prds(version_id=version_id, user_id=int(user["id"])))


@router.post("/api/v1/project-versions/{version_id}/prds", status_code=201)
def create_prd(version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_requirement_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.create_prd(version_id=version_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/prds/{prd_id}")
def get_prd(prd_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.get_prd(prd_id=prd_id, user_id=int(user["id"])))


@router.get("/api/v1/prd-versions/{version_id}")
def get_prd_version(version_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.get_version(version_id=version_id, user_id=int(user["id"])))


@router.post("/api/v1/prds/{prd_id}/versions", status_code=201)
def create_prd_version(prd_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_requirement_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.save_version(prd_id=prd_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))


@router.post("/api/v1/project-versions/{version_id}/design-reviews", status_code=201)
def submit_design_review(version_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_requirement_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.submit_review(version_id=version_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))


@router.get("/api/v1/design-reviews/{review_id}")
def get_design_review(review_id: int, request: Request, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.get_review(review_id=review_id, user_id=int(user["id"])))


@router.post("/api/v1/design-reviews/{review_id}:decide")
def decide_design_review(review_id: int, request: Request, body: Annotated[dict[str, Any], Body()], key: Annotated[str, Depends(require_requirement_idempotency_key)], authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    user = auth_service.authenticate(authorization)
    return _ok(request, service.decide_review(review_id=review_id, user_id=int(user["id"]), payload=body, key=key, trace_id=request.state.trace_id))
