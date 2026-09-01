from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import ai_tasks as routes
from app.main import app
from app.modules.ai_tasks import service as task_service
from app.platform.errors import ApiError


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "_Rows":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Connection:
    def __init__(self, tasks: list[dict[str, Any]], refs: dict[int, list[dict[str, Any]]]) -> None:
        self.tasks = tasks
        self.refs = refs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any]) -> _Rows:
        sql = " ".join(str(statement).split())
        self.calls.append((sql, params))
        if "SELECT at.* FROM ai_task at" in sql:
            return _Rows(self.tasks)
        return _Rows(self.refs.get(int(params["task_id"]), []))


def _task(task_id: int, *, status: str = "ready") -> dict[str, Any]:
    return {
        "id": task_id,
        "task_public_id": f"85cb6e8e-f36f-4d52-b98f-7a8466da{task_id:04d}",
        "status": status,
        "task_type": "requirement.clarify",
        "user_id": 7,
        "queued_at": datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
        "target_snapshot_hash": "a" * 64,
        "capability_summary": {},
        "missing_items": [],
    }


def _ref() -> dict[str, Any]:
    return {
        "ai_result_id": 17,
        "ai_call_id": 9,
        "result_no": 1,
        "status": "ready",
        "target_snapshot_hash": "a" * 64,
        "content_ref": "private/results/task/17.json",
        "content_fingerprint": "b" * 64,
    }


def test_list_tasks_filters_visible_authoritative_rows_and_projects_public_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection([_task(22)], {22: [_ref()]})

    @contextmanager
    def fake_readonly():
        yield connection

    monkeypatch.setattr(task_service, "readonly", fake_readonly)
    result = task_service.AiTaskService().list_tasks(
        user_id=7,
        project_id="10",
        status="ready",
        cursor="30",
    )

    sql, params = connection.calls[0]
    assert "EXISTS (SELECT 1 FROM project_member pm" in sql
    assert "pm.role_code IN ('owner','reviewer','implementer','tester')" in sql
    assert "at.project_id=:project_id" in sql
    assert "at.status=:status" in sql
    assert "at.id<:cursor" in sql
    assert params == {
        "user_id": 7,
        "project_id": 10,
        "status": "ready",
        "cursor": 30,
        "limit": 21,
    }
    assert result["has_more"] is False
    assert result["next_cursor"] is None
    assert result["items"][0]["result_refs"] == [{
        "result_id": "17",
        "status": "ready",
        "target_snapshot_hash": "a" * 64,
    }]
    serialized = str(result)
    assert "content_ref" not in serialized
    assert "content_fingerprint" not in serialized


def test_list_tasks_authorized_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = _Connection([], {})

    @contextmanager
    def fake_readonly():
        yield connection

    monkeypatch.setattr(task_service, "readonly", fake_readonly)
    assert task_service.AiTaskService().list_tasks(user_id=7) == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
    }


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"project_id": "0"}, "project_id"),
        ({"project_id": "01"}, "project_id"),
        ({"cursor": "bad"}, "cursor"),
        ({"status": "unknown"}, "status"),
    ],
)
def test_list_tasks_rejects_invalid_filters(kwargs: dict[str, str], field: str) -> None:
    with pytest.raises(ApiError) as caught:
        task_service.AiTaskService().list_tasks(user_id=7, **kwargs)
    assert (caught.value.code, caught.value.http_status) == ("VALIDATION_ERROR", 422)
    assert field in caught.value.message


def test_get_ai_tasks_route_is_registered_and_forwards_frozen_filters() -> None:
    data = {"items": [], "next_cursor": None, "has_more": False}
    with (
        patch.object(routes.auth_service, "authenticate", return_value={"id": 7}),
        patch.object(routes.service, "list_tasks", return_value=data) as list_tasks,
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/ai/tasks?project_id=10&status=ready&cursor=30",
            headers={"Authorization": "Bearer test"},
        )
    assert response.status_code == 200
    assert response.json()["data"] == data
    list_tasks.assert_called_once_with(
        user_id=7,
        project_id="10",
        status="ready",
        cursor="30",
    )


def test_get_ai_tasks_requires_authentication() -> None:
    with (
        patch.object(
            routes.auth_service,
            "authenticate",
            side_effect=ApiError("AUTH_REQUIRED", "Authentication required", 401),
        ),
        patch.object(routes.service, "list_tasks") as list_tasks,
        TestClient(app) as client,
    ):
        response = client.get("/api/v1/ai/tasks")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
    list_tasks.assert_not_called()
