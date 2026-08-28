from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.ai_tasks.service import AiTaskService, _canonical_hash
from app.modules.requirements.service import _empty_content
from app.platform.errors import ApiError


class _Rows:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _LookupConnection:
    def __init__(self, *, candidate_ids: list[int], member: bool = True) -> None:
        content, _ = _empty_content("raw requirement", requirement_id=6, title="Requirement")
        content["clarification"]["mode"] = "standard"
        content_hash = _canonical_hash(content)
        self.version = {
            "id": 29,
            "requirement_id": 6,
            "content_json": content,
            "content_hash": content_hash,
        }
        self.requirement = {"id": 6, "project_version_id": 9}
        self.project_version = {"id": 9, "project_id": 8}
        self.candidate_ids = candidate_ids
        self.member = member
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, dict(params)))
        if sql.startswith("SELECT * FROM requirement_version WHERE id="):
            return _Rows([self.version] if int(params["version_id"]) == 29 else [])
        if sql.startswith("SELECT * FROM requirement WHERE id="):
            return _Rows([self.requirement] if int(params["requirement_id"]) == 6 else [])
        if sql.startswith("SELECT id,project_id FROM project_version"):
            return _Rows([self.project_version] if int(params["id"]) == 9 else [])
        if "SELECT role_code FROM project_member" in sql:
            return _Rows([{"role_code": "owner"}] if self.member else [])
        if sql.startswith("SELECT ar.id FROM ai_result"):
            return _Rows([{"id": result_id} for result_id in self.candidate_ids])
        raise AssertionError(f"Unhandled SQL: {sql}")


def _result(connection: _LookupConnection, result_id: str = "4", **overrides):
    content = {
        "result_kind": "questions",
        "mode": "standard",
        "round_no": 1,
        "questions": [{"question_id": "q-1"}],
    }
    value = {
        "id": result_id,
        "task_public_id": "2169067d-1f72-e6d5-6ace-58e25f2c8dbd",
        "task_type": "requirement.clarify",
        "status": "ready",
        "result_kind": "questions",
        "mode": "standard",
        "round_no": 1,
        "target_snapshot_hash": connection.version["content_hash"],
        "content_json": content,
    }
    value.update(overrides)
    return value


def _read(service: AiTaskService, connection: _LookupConnection, **overrides):
    @contextmanager
    def read_scope():
        yield connection

    with patch("app.modules.ai_tasks.service.readonly", read_scope):
        return service.get_authoritative_questions_result_for_version(
            user_id=overrides.get("user_id", 10),
            requirement_version_id=overrides.get("requirement_version_id", 29),
            mode=overrides.get("mode", "standard"),
            round_no=overrides.get("round_no", 1),
        )


def test_exact_ready_questions_result_uses_canonical_validation_without_side_effects() -> None:
    connection = _LookupConnection(candidate_ids=[4])
    client = MagicMock()
    service = AiTaskService(client=client)
    client.reset_mock()
    canonical = _result(connection)
    service.get_result = MagicMock(return_value=canonical)

    assert _read(service, connection) == canonical
    service.get_result.assert_called_once_with(user_id=10, result_id="4")
    assert not client.mock_calls
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _ in connection.calls)
    candidate_sql, candidate_params = next(
        (sql, params) for sql, params in connection.calls if sql.startswith("SELECT ar.id FROM ai_result")
    )
    for predicate in (
        "at.task_type='requirement.clarify'",
        "at.status='ready'",
        "ac.status='succeeded'",
        "ar.status='ready'",
    ):
        assert predicate in candidate_sql
    assert candidate_params == {
        "project_id": 8,
        "project_version_id": 9,
        "requirement_id": 6,
        "requirement_version_id": 29,
        "target_snapshot_hash": connection.version["content_hash"],
    }


@pytest.mark.parametrize(
    ("candidate_ids", "results", "expected"),
    [
        ([], {}, ("RESOURCE_NOT_FOUND", 404)),
        ([4, 5], None, ("CLARIFICATION_ROUND_INVALID", 409)),
    ],
)
def test_zero_is_not_found_and_ambiguous_results_fail_closed(candidate_ids, results, expected) -> None:
    connection = _LookupConnection(candidate_ids=candidate_ids)
    service = AiTaskService(client=MagicMock())
    candidates = results or {str(item): _result(connection, str(item)) for item in candidate_ids}
    service.get_result = MagicMock(side_effect=lambda *, user_id, result_id: candidates[result_id])

    with pytest.raises(ApiError) as raised:
        _read(service, connection)
    assert (raised.value.code, raised.value.http_status) == expected


def test_wrong_target_version_mode_and_round_are_not_returned() -> None:
    for override in (
        {"requirement_version_id": 30},
        {"mode": "deep"},
        {"round_no": 2},
    ):
        connection = _LookupConnection(candidate_ids=[4])
        service = AiTaskService(client=MagicMock())
        service.get_result = MagicMock(return_value=_result(connection))
        with pytest.raises(ApiError) as raised:
            _read(service, connection, **override)
        assert (raised.value.code, raised.value.http_status) == ("RESOURCE_NOT_FOUND", 404)
        service.get_result.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_snapshot_hash": "b" * 64},
        {"mode": "deep", "content_json": {"result_kind": "questions", "mode": "deep", "round_no": 1}},
        {"round_no": 2, "content_json": {"result_kind": "questions", "mode": "standard", "round_no": 2}},
        {"status": "failed"},
        {"result_kind": "baseline", "content_json": {"result_kind": "baseline", "mode": "standard", "round_no": 1}},
    ],
)
def test_nonmatching_or_nonready_candidate_is_not_returned(overrides) -> None:
    connection = _LookupConnection(candidate_ids=[4])
    service = AiTaskService(client=MagicMock())
    service.get_result = MagicMock(return_value=_result(connection, **overrides))
    with pytest.raises(ApiError) as raised:
        _read(service, connection)
    assert (raised.value.code, raised.value.http_status) == ("RESOURCE_NOT_FOUND", 404)


def test_authoritative_get_result_validation_failure_is_propagated() -> None:
    connection = _LookupConnection(candidate_ids=[4])
    service = AiTaskService(client=MagicMock())
    service.get_result = MagicMock(
        side_effect=ApiError("TRACEABILITY_INCOMPLETE", "AI result target is inconsistent", 409)
    )
    with pytest.raises(ApiError) as raised:
        _read(service, connection)
    assert (raised.value.code, raised.value.http_status) == ("TRACEABILITY_INCOMPLETE", 409)


def test_addressed_version_hash_and_project_membership_fail_closed() -> None:
    invalid_hash = _LookupConnection(candidate_ids=[4])
    invalid_hash.version["content_hash"] = "b" * 64
    service = AiTaskService(client=MagicMock())
    service.get_result = MagicMock(return_value=_result(invalid_hash))
    with pytest.raises(ApiError) as raised:
        _read(service, invalid_hash)
    assert (raised.value.code, raised.value.http_status) == ("TRACEABILITY_INCOMPLETE", 409)
    service.get_result.assert_not_called()

    unauthorized = _LookupConnection(candidate_ids=[4], member=False)
    with pytest.raises(ApiError) as raised:
        _read(AiTaskService(client=MagicMock()), unauthorized)
    assert (raised.value.code, raised.value.http_status) == ("RESOURCE_NOT_FOUND", 404)


def test_public_route_returns_existing_ai_result_envelope_and_no_idempotency_header() -> None:
    result = {"id": "4", "task_public_id": "task-1", "result_kind": "questions"}
    with (
        patch("app.api.v1.requirements.auth_service.authenticate", return_value={"id": 10}),
        patch(
            "app.api.v1.requirements.ai_result_service.get_authoritative_questions_result_for_version",
            return_value=result,
        ) as lookup,
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/requirement-versions/29/clarification-result?mode=standard&round_no=1",
            headers={"Authorization": "Bearer test"},
        )
    assert response.status_code == 200
    assert response.json()["data"] == result
    lookup.assert_called_once_with(
        user_id=10,
        requirement_version_id=29,
        mode="standard",
        round_no=1,
    )
