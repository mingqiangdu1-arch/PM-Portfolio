from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from app.modules.confirmation.service import (
    _body_id,
    _digest,
    _id,
    _map_database_error,
    _plan_content,
    _readiness,
    _summary,
)
from app.platform.errors import ApiError


def _content() -> dict:
    item = {"key": "scope.one", "description": "A bounded implementation scope"}
    return {
        "schema_version": "implementation_plan.mvp3.v1",
        "features": [item],
        "business_rules": [],
        "state_requirements": [],
        "exceptions": [],
        "interactions": [],
        "dependencies": [],
        "acceptance_scope": [
            {"key": "acceptance.one", "description": "A bounded acceptance scope"}
        ],
    }


def _readiness_data(**changes: object) -> dict:
    value = {
        "schema_version": "implementation_confirmation.readiness.mvp3.v1",
        "scope_status": "ready",
        "implementation_status": "ready",
        "configuration_status": "not_applicable",
        "data_change_status": "not_applicable",
        "known_blockers": [],
    }
    value.update(changes)
    return value


def test_frozen_content_is_normalized_and_hashed_as_utf8() -> None:
    value = _content()
    value["features"][0]["description"] = "  A bounded implementation scope\r\n"
    normalized = _plan_content(value)
    assert normalized["features"][0]["description"] == "A bounded implementation scope"
    assert len(_digest(normalized)) == 64


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {"schema_version": "bad"},
        {"schema_version": "implementation_plan.mvp3.v1", "features": []},
    ],
)
def test_invalid_content_is_rejected(bad: object) -> None:
    with pytest.raises(ApiError) as raised:
        _plan_content(bad)
    assert raised.value.code == "VALIDATION_ERROR"


def test_duplicate_keys_and_nulls_are_rejected() -> None:
    value = _content()
    value["acceptance_scope"][0]["key"] = "scope.one"
    with pytest.raises(ApiError):
        _plan_content(value)
    value = _content()
    value["features"][0]["description"] = None
    with pytest.raises(ApiError):
        _plan_content(value)


def test_readiness_completion_predicate_inputs_are_strict() -> None:
    assert _readiness(_readiness_data())["known_blockers"] == []
    with pytest.raises(ApiError):
        _readiness(_readiness_data(known_blockers=["same", "same"]))
    with pytest.raises(ApiError):
        _summary("too short")
    assert _id("7", "id") == 7
    with pytest.raises(ApiError):
        _body_id(7, "plan_version_id")


@pytest.mark.parametrize("driver_code", ["1213", "1205"])
def test_mysql_concurrency_errors_map_to_version_conflict(driver_code: str) -> None:
    error = OperationalError("UPDATE confirmation_round", {}, Exception(driver_code))
    mapped = _map_database_error(error)
    assert mapped.code == "VERSION_CONFLICT"
    assert mapped.http_status == 409
