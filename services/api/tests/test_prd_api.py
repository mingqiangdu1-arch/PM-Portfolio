from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.api.v1 import prds as prd_routes
from app.main import app
from app.modules.prds.service import PrdService
from app.platform.errors import ApiError


class StubService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _call(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        return {"operation": name}

    def list_prds(self, **kwargs): return self._call("list", **kwargs)
    def create_prd(self, **kwargs): return self._call("create", **kwargs)
    def get_prd(self, **kwargs): return self._call("get_prd", **kwargs)
    def get_version(self, **kwargs): return self._call("get_version", **kwargs)
    def save_version(self, **kwargs): return self._call("save", **kwargs)
    def submit_review(self, **kwargs): return self._call("submit", **kwargs)
    def get_review(self, **kwargs): return self._call("get_review", **kwargs)
    def decide_review(self, **kwargs): return self._call("decide", **kwargs)


def test_all_frozen_prd_routes_delegate_to_the_aggregate_service(monkeypatch) -> None:
    service = StubService()
    monkeypatch.setattr(prd_routes, "service", service)
    monkeypatch.setattr(prd_routes.auth_service, "authenticate", lambda _header: {"id": 7})
    client = TestClient(app)
    headers = {"Authorization": "Bearer test", "Idempotency-Key": "mvp2-route-key"}
    requests = [
        ("get", "/api/v1/project-versions/10/prds", None, "list"),
        ("post", "/api/v1/project-versions/10/prds", {"source_requirement_version_id": "20", "name": "PRD"}, "create"),
        ("get", "/api/v1/prds/30", None, "get_prd"),
        ("get", "/api/v1/prd-versions/40", None, "get_version"),
        ("post", "/api/v1/prds/30/versions", {"expected_version": 1, "content_json": {}, "change_note": "save"}, "save"),
        ("post", "/api/v1/project-versions/10/design-reviews", {"prd_id": "30", "prd_version_id": "40", "content_hash": "a" * 64, "expected_version": 2}, "submit"),
        ("get", "/api/v1/design-reviews/50", None, "get_review"),
        ("post", "/api/v1/design-reviews/50:decide", {"expected_version": 1, "decision": "pass"}, "decide"),
    ]
    for method, path, body, operation in requests:
        if method == "get":
            response = client.get(path, headers=headers)
        else:
            response = client.post(path, json=body, headers=headers)
        assert response.status_code == (201 if operation in {"create", "save", "submit"} else 200)
        assert response.json()["data"]["operation"] == operation
    assert [name for name, _ in service.calls] == [item[3] for item in requests]


@pytest.mark.parametrize(
    ("operation", "payload"),
    [
        ("create", {"source_requirement_version_id": "1"}),
        ("create", {"source_requirement_version_id": "1", "name": "PRD", "unexpected": True}),
        ("save", {"expected_version": 1, "content_json": {}, "change_note": "save", "unexpected": True}),
        ("submit", {"prd_id": "1", "prd_version_id": "1", "content_hash": "A" * 64, "expected_version": 1}),
        ("submit", {"prd_id": "1", "prd_version_id": "1", "content_hash": "a" * 64}),
        ("decide", {"expected_version": 1, "decision": "changes_requested"}),
        ("decide", {"expected_version": 1, "decision": "pass", "summary": "not allowed"}),
    ],
)
def test_frozen_prd_requests_reject_missing_unknown_or_invalid_top_level_fields(operation: str, payload: dict) -> None:
    service = PrdService()
    with pytest.raises(ApiError) as error:
        if operation == "create":
            service.create_prd(version_id=1, user_id=1, payload=payload, key="key", trace_id="trace")
        elif operation == "save":
            service.save_version(prd_id=1, user_id=1, payload=payload, key="key", trace_id="trace")
        elif operation == "submit":
            service.submit_review(version_id=1, user_id=1, payload=payload, key="key", trace_id="trace")
        else:
            service.decide_review(review_id=1, user_id=1, payload=payload, key="key", trace_id="trace")
    assert error.value.code == "VALIDATION_ERROR"
