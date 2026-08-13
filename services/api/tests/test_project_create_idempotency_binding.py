from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from app.api.v1.sprint1 import router
from app.platform.errors import install_exception_handlers
from app.platform.trace import TraceMiddleware


def _test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceMiddleware)
    app.include_router(router)
    install_exception_handlers(app)
    return app


def _create_project_route(app: FastAPI):
    def find(routes):
        for route in routes:
            if (
                getattr(route, "path", None) == "/api/v1/projects"
                and "POST" in getattr(route, "methods", set())
            ):
                return route
            nested = getattr(route, "routes", None)
            if nested and (match := find(nested)) is not None:
                return match
            original_router = getattr(route, "original_router", None)
            if original_router is not None and (
                match := find(original_router.routes)
            ) is not None:
                return match
        return None

    route = find(app.routes)
    assert route is not None
    return route


def test_valid_idempotency_header_binds_without_query_key() -> None:
    app = _test_app()
    created = {
        "project": {"id": "1"},
        "version": {"id": "2"},
        "working_version_id": "2",
    }
    with (
        patch("app.api.v1.sprint1.service.authenticate", return_value={"id": 10}),
        patch("app.api.v1.sprint1.service.create_project", return_value=created) as create,
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/projects",
            headers={
                "Authorization": "Bearer test",
                "Idempotency-Key": "project-create-key",
            },
            json={"name": "Gate project", "start_mode": "new"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == created
    assert create.call_args.kwargs["key"] == "project-create-key"


def test_missing_idempotency_header_uses_existing_rejection() -> None:
    app = _test_app()
    with (
        patch("app.api.v1.sprint1.service.authenticate", return_value={"id": 10}),
        patch("app.api.v1.sprint1.service.create_project") as create,
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/projects",
            headers={"Authorization": "Bearer test"},
            json={"name": "Gate project", "start_mode": "new"},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    create.assert_not_called()


def test_runtime_and_generated_route_expose_header_not_query_key() -> None:
    app = _test_app()
    route = _create_project_route(app)

    assert not any(parameter.alias == "key" for parameter in route.dependant.query_params)
    assert [parameter.alias for parameter in route.dependant.header_params] == ["authorization"]
    assert [(dependency.name, dependency.call) for dependency in route.dependant.dependencies] == [
        ("key", route.endpoint.__globals__["require_idempotency_key"])
    ]

    original_include = route.include_in_schema
    route.include_in_schema = True
    try:
        schema = get_openapi(title="test", version="test", routes=[route])
    finally:
        route.include_in_schema = original_include

    parameters = schema["paths"]["/api/v1/projects"]["post"]["parameters"]
    assert any(
        parameter["in"] == "header"
        and parameter["name"] == "Idempotency-Key"
        for parameter in parameters
    )
    assert not any(
        parameter["in"] == "query" and parameter["name"] == "key"
        for parameter in parameters
    )
