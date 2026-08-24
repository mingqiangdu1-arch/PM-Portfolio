from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import implementation_plans
from app.platform.errors import install_exception_handlers


RECORD = {
    "test_record": {
        "id": "9",
        "confirmation_round_id": "3",
        "title": "Smoke test",
        "test_type": "manual",
        "scope": "save and submit",
        "environment": {"name": "local", "preconditions": []},
        "steps": ["run"],
        "expected_result": "passes",
        "actual_result": "passes",
        "result_status": "success",
        "tester_id": "10",
        "status": "draft",
        "submitted_at": None,
        "row_version": 1,
        "created_at": "2026-08-24T00:00:00Z",
        "updated_at": "2026-08-24T00:00:00Z",
    }
}


def _app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def trace(request, call_next):
        request.state.trace_id = "trace-mvp4-api-test"
        return await call_next(request)

    app.include_router(implementation_plans.router)
    install_exception_handlers(app)
    return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        implementation_plans.auth_service, "authenticate", lambda _authorization: {"id": "10"}
    )
    monkeypatch.setattr(implementation_plans.service, "list_test_records", lambda **_: {"items": []})
    monkeypatch.setattr(implementation_plans.service, "create_test_record", lambda **_: RECORD)
    monkeypatch.setattr(implementation_plans.service, "get_test_record", lambda **_: RECORD)
    monkeypatch.setattr(implementation_plans.service, "update_test_record", lambda **_: RECORD)
    monkeypatch.setattr(implementation_plans.service, "submit_test_record", lambda **_: RECORD)
    with TestClient(_app()) as value:
        yield value


def test_frozen_five_operations_return_standard_envelopes(client: TestClient) -> None:
    body = {
        "title": "Smoke test",
        "scope": "save and submit",
        "environment": {"name": "local", "preconditions": []},
        "steps": ["run"],
        "expected_result": "passes",
        "actual_result": "passes",
        "result_status": "success",
    }
    requests = [
        ("GET", "/api/v1/confirmation-rounds/3/test-records", {}, 200),
        (
            "POST",
            "/api/v1/confirmation-rounds/3/test-records",
            {"json": body, "headers": {"Idempotency-Key": "mvp4-create-1"}},
            201,
        ),
        ("GET", "/api/v1/test-records/9", {}, 200),
        (
            "PATCH",
            "/api/v1/test-records/9",
            {"json": {"expected_version": 1, "scope": "updated"}},
            200,
        ),
        (
            "POST",
            "/api/v1/test-records/9:submit",
            {"json": {"expected_version": 1}, "headers": {"Idempotency-Key": "mvp4-submit-1"}},
            200,
        ),
    ]
    for method, path, kwargs, expected_status in requests:
        headers = {"Authorization": "Bearer test", **kwargs.pop("headers", {})}
        response = client.request(method, path, headers=headers, **kwargs)
        assert response.status_code == expected_status, response.text
        assert set(response.json()) == {"code", "message", "data", "trace_id"}
        assert response.json()["trace_id"] == "trace-mvp4-api-test"


def test_create_and_submit_require_idempotency_and_path_ids(client: TestClient) -> None:
    body = {"title": "Smoke test"}
    missing = client.post(
        "/api/v1/confirmation-rounds/3/test-records",
        json=body,
        headers={"Authorization": "Bearer test"},
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "VALIDATION_ERROR")
    invalid_path = client.get(
        "/api/v1/confirmation-rounds/01/test-records",
        headers={"Authorization": "Bearer test"},
    )
    assert (invalid_path.status_code, invalid_path.json()["code"]) == (422, "VALIDATION_ERROR")
    invalid_submit = client.post(
        "/api/v1/test-records/9:submit",
        json={"expected_version": 1},
        headers={"Authorization": "Bearer test", "Idempotency-Key": "short"},
    )
    assert (invalid_submit.status_code, invalid_submit.json()["code"]) == (422, "VALIDATION_ERROR")


def test_patch_rejects_idempotency_header(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/test-records/9",
        json={"expected_version": 1, "scope": "updated"},
        headers={"Authorization": "Bearer test", "Idempotency-Key": "mvp4-patch-1"},
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
