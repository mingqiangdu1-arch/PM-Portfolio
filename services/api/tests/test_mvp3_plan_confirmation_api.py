from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import implementation_plans
from app.platform.errors import install_exception_handlers


def _app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def trace(request, call_next):
        request.state.trace_id = "trace-api-test"
        return await call_next(request)

    app.include_router(implementation_plans.router)
    install_exception_handlers(app)
    return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        implementation_plans.auth_service, "authenticate", lambda _authorization: {"id": "10"}
    )
    empty_plan = {"implementation_plan": {"id": "1"}}
    empty_version = {"implementation_plan_version": {"id": "2"}, "plan_row_version": 2}
    empty_round = {"confirmation_round": {"id": "3"}}
    monkeypatch.setattr(implementation_plans.service, "list_plans", lambda **_: {"items": []})
    monkeypatch.setattr(implementation_plans.service, "create_plan", lambda **_: empty_plan)
    monkeypatch.setattr(implementation_plans.service, "get_plan", lambda **_: empty_plan)
    monkeypatch.setattr(
        implementation_plans.service, "create_plan_version", lambda **_: empty_version
    )
    monkeypatch.setattr(implementation_plans.service, "set_effective", lambda **_: empty_plan)
    monkeypatch.setattr(implementation_plans.service, "list_rounds", lambda **_: {"items": []})
    monkeypatch.setattr(implementation_plans.service, "create_round", lambda **_: empty_round)
    monkeypatch.setattr(implementation_plans.service, "get_round", lambda **_: empty_round)
    monkeypatch.setattr(implementation_plans.service, "update_round", lambda **_: empty_round)
    monkeypatch.setattr(implementation_plans.service, "confirm_round", lambda **_: empty_round)
    with TestClient(_app()) as value:
        yield value


def test_all_ten_hidden_adapters_return_envelopes_and_expected_statuses(client: TestClient) -> None:
    headers = {"Authorization": "Bearer test", "Idempotency-Key": "mvp3-key-1"}
    body = {"source_prd_version_id": "4", "source_design_review_id": "5", "name": "Plan"}
    content = {"expected_version": 1, "content_json": {}, "change_note": "note"}
    round_body = {
        "plan_version_id": "2",
        "implementation_summary": "A sufficiently long implementation summary.",
        "readiness_json": {},
    }
    requests = [
        ("GET", "/api/v1/project-versions/1/implementation-plans", {}, 200),
        (
            "POST",
            "/api/v1/project-versions/1/implementation-plans",
            {"json": body, "headers": headers},
            201,
        ),
        ("GET", "/api/v1/implementation-plans/1", {}, 200),
        (
            "POST",
            "/api/v1/implementation-plans/1/versions",
            {"json": content, "headers": headers},
            201,
        ),
        (
            "POST",
            "/api/v1/plan-versions/2:set-effective",
            {"json": {"expected_version": 2}, "headers": headers},
            200,
        ),
        ("GET", "/api/v1/implementation-plans/1/confirmation-rounds", {}, 200),
        (
            "POST",
            "/api/v1/implementation-plans/1/confirmation-rounds",
            {"json": round_body, "headers": headers},
            201,
        ),
        ("GET", "/api/v1/confirmation-rounds/3", {}, 200),
        (
            "PATCH",
            "/api/v1/confirmation-rounds/3",
            {"json": {"expected_version": 1, **round_body}},
            200,
        ),
        (
            "POST",
            "/api/v1/confirmation-rounds/3:confirm",
            {"json": {"expected_version": 1}, "headers": headers},
            200,
        ),
    ]
    for method, path, kwargs, status in requests:
        response = client.request(
            method,
            path,
            headers={"Authorization": "Bearer test", **kwargs.pop("headers", {})},
            **kwargs,
        )
        assert response.status_code == status, response.text
        payload = response.json()
        assert set(payload) == {"code", "message", "data", "trace_id"}
        assert payload["trace_id"] == "trace-api-test"


def test_idempotency_and_patch_header_rules(client: TestClient) -> None:
    body = {"source_prd_version_id": "4", "source_design_review_id": "5", "name": "Plan"}
    missing = client.post(
        "/api/v1/project-versions/1/implementation-plans",
        json=body,
        headers={"Authorization": "Bearer test"},
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "VALIDATION_ERROR")
    short = client.post(
        "/api/v1/project-versions/1/implementation-plans",
        json=body,
        headers={"Authorization": "Bearer test", "Idempotency-Key": "short"},
    )
    assert (short.status_code, short.json()["code"]) == (422, "VALIDATION_ERROR")
    patch = client.patch(
        "/api/v1/confirmation-rounds/3",
        json={
            "expected_version": 1,
            "plan_version_id": "2",
            "implementation_summary": "A sufficiently long implementation summary.",
            "readiness_json": {},
        },
        headers={"Authorization": "Bearer test", "Idempotency-Key": "mvp3-key-1"},
    )
    assert (patch.status_code, patch.json()["code"]) == (422, "VALIDATION_ERROR")


def test_path_ids_are_lexically_string_validated(client: TestClient) -> None:
    response = client.get(
        "/api/v1/implementation-plans/01", headers={"Authorization": "Bearer test"}
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    numeric_body = client.post(
        "/api/v1/project-versions/1/implementation-plans",
        json={"source_prd_version_id": 4, "source_design_review_id": "5", "name": "Plan"},
        headers={"Authorization": "Bearer test", "Idempotency-Key": "mvp3-key-2"},
    )
    assert (numeric_body.status_code, numeric_body.json()["code"]) == (422, "VALIDATION_ERROR")
