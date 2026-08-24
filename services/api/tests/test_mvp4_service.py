from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.modules.confirmation import service as confirmation_module
from app.platform.errors import ApiError


class _Result:
    def __init__(self, rows=None, *, rowcount: int = 0, lastrowid: int | None = None):
        self.rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _TestRecordDB:
    """Low-cost SQL fake exercising the real MVP4 service transaction paths."""

    def __init__(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        self.round = {
            "id": 3,
            "status": "confirmed",
            "confirm_status": "confirmed",
            "is_effective": True,
            "plan_version_id": 20,
            "implementation_plan_id": 10,
        }
        self.plan = {
            "id": 10,
            "project_version_id": 7,
            "status": "active",
            "current_version_id": 20,
            "archived_at": None,
        }
        self.plan_version = {"id": 20, "implementation_plan_id": 10, "is_effective": True}
        self.project_version = {"id": 7, "project_id": 99, "archived_at": None}
        self.members = [
            {"project_id": 99, "user_id": 10, "role_code": "owner", "status": "active"}
        ]
        self.records: list[dict] = []
        self.idempotency: list[dict] = []
        self.audit: list[dict] = []
        self.outbox: list[dict] = []
        self.next_record_id = 100
        self.now = now
        self.fail_on_outbox = False
        self.calls: list[str] = []

    @contextmanager
    def transaction(self):
        snapshot = copy.deepcopy(self.__dict__)
        try:
            yield self
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(snapshot)
            raise

    def _source(self) -> dict:
        return {
            "round_id": self.round["id"],
            "round_status": self.round["status"],
            "confirm_status": self.round["confirm_status"],
            "round_effective": self.round["is_effective"],
            "plan_version_id": self.round["plan_version_id"],
            "plan_id": self.plan["id"],
            "project_version_id": self.plan["project_version_id"],
            "plan_status": self.plan["status"],
            "current_version_id": self.plan["current_version_id"],
            "plan_version_plan_id": self.plan_version["implementation_plan_id"],
            "plan_version_effective": self.plan_version["is_effective"],
            "project_id": self.project_version["project_id"],
        }

    def _identity(self, record_id: int) -> dict | None:
        row = next((item for item in self.records if item["id"] == record_id), None)
        if not row:
            return None
        return {
            **row,
            "implementation_plan_id": self.plan["id"],
            "project_version_id": self.plan["project_version_id"],
            "project_id": self.project_version["project_id"],
        }

    def execute(self, statement, params=None):
        sql = str(statement).strip()
        self.calls.append(sql)
        params = params or {}
        if sql.startswith("SELECT r.id AS round_id"):
            return _Result([self._source()])
        if sql.startswith("SELECT tr.*,r.implementation_plan_id"):
            row = self._identity(int(params["id"]))
            return _Result([row] if row else [])
        if "SELECT role_code FROM project_member" in sql:
            rows = [
                row
                for row in self.members
                if row["project_id"] == params["project_id"]
                and row["user_id"] == params["user_id"]
                and row["status"] == "active"
            ]
            return _Result(rows)
        if sql.startswith("INSERT IGNORE INTO idempotency_record"):
            found = next(
                (
                    row
                    for row in self.idempotency
                    if (row["user_id"], row["endpoint_key"], row["idempotency_key"])
                    == (params["user_id"], params["endpoint"], params["key"])
                ),
                None,
            )
            if found:
                return _Result(rowcount=0)
            self.idempotency.append(
                {
                    "user_id": params["user_id"],
                    "endpoint_key": params["endpoint"],
                    "idempotency_key": params["key"],
                    "request_hash": params["digest"],
                    "status": "in_progress",
                    "response_ref": None,
                }
            )
            return _Result(rowcount=1)
        if "SELECT request_hash,status,response_ref FROM idempotency_record" in sql:
            row = next(
                (
                    item
                    for item in self.idempotency
                    if (item["user_id"], item["endpoint_key"], item["idempotency_key"])
                    == (params["user_id"], params["endpoint"], params["key"])
                ),
                None,
            )
            return _Result([row] if row else [])
        if sql.startswith("UPDATE idempotency_record"):
            row = next(
                item
                for item in self.idempotency
                if (item["user_id"], item["endpoint_key"], item["idempotency_key"])
                == (params["user_id"], params["endpoint"], params["key"])
            )
            row.update(status="completed", response_ref=params["ref"])
            return _Result(rowcount=1)
        if sql.startswith("INSERT INTO test_record"):
            record_id = self.next_record_id
            self.next_record_id += 1
            self.records.append(
                {
                    "id": record_id,
                    "confirmation_round_id": params["round_id"],
                    "title": params["title"],
                    "scope": params["scope"],
                    "environment_json": params["environment"],
                    "steps_json": params["steps"],
                    "expected_result": params["expected"],
                    "actual_result": params["actual"],
                    "result_status": params["result_status"],
                    "tester_id": params["uid"],
                    "submitted_at": None,
                    "row_version": 1,
                    "created_at": params["now"],
                    "updated_at": params["now"],
                }
            )
            return _Result(rowcount=1, lastrowid=record_id)
        if sql.startswith("SELECT * FROM test_record WHERE id="):
            row = next((item for item in self.records if item["id"] == params["id"]), None)
            return _Result([row] if row else [])
        if sql.startswith("UPDATE test_record SET submitted_at="):
            row = next(item for item in self.records if item["id"] == params["id"])
            row.update(submitted_at=params["now"], updated_at=params["now"], row_version=row["row_version"] + 1)
            return _Result(rowcount=1)
        if sql.startswith("UPDATE test_record SET "):
            row = next(item for item in self.records if item["id"] == params["id"])
            for field in ("scope", "environment_json", "steps_json", "expected_result", "actual_result", "result_status"):
                if field in params:
                    row[field] = params[field]
            row.update(updated_at=params["now"], row_version=row["row_version"] + 1)
            return _Result(rowcount=1)
        if sql.startswith("INSERT INTO operation_audit_log"):
            self.audit.append(params.copy())
            return _Result(rowcount=1, lastrowid=len(self.audit))
        if sql.startswith("INSERT INTO business_event_outbox"):
            if self.fail_on_outbox:
                raise RuntimeError("outbox failed")
            self.outbox.append(params.copy())
            return _Result(rowcount=1)
        raise AssertionError(f"Unhandled SQL: {sql}")


@pytest.fixture
def service_db():
    db = _TestRecordDB()
    with patch.object(confirmation_module, "transaction", db.transaction):
        yield confirmation_module.service, db


def _payload(*, complete: bool = True, title: str = "Smoke test") -> dict:
    return {
        "title": title,
        "scope": "scope" if complete else "",
        "environment": {"name": "local" if complete else "", "preconditions": []},
        "steps": ["run"] if complete else [],
        "expected_result": "passes" if complete else "",
        "actual_result": "passes" if complete else "",
        "result_status": "success",
    }


def test_create_validates_title_and_allows_incomplete_draft_environment(service_db):
    service, _ = service_db
    with pytest.raises(ApiError) as too_long:
        service.create_test_record(round_id=3, user_id=10, payload=_payload(title="x" * 201), key="title-key", trace_id="trace")
    assert (too_long.value.code, too_long.value.http_status) == ("VALIDATION_ERROR", 422)

    created = service.create_test_record(
        round_id=3, user_id=10, payload=_payload(complete=False), key="draft-key", trace_id="trace"
    )
    assert created["test_record"]["status"] == "draft"
    assert created["test_record"]["environment"]["name"] == ""


def test_service_update_submit_replay_context_and_minimal_audit(service_db):
    service, db = service_db
    first = service.create_test_record(
        round_id=3, user_id=10, payload=_payload(), key="create-key", trace_id="trace-create"
    )
    record_id = int(first["test_record"]["id"])

    updated = service.update_test_record(
        record_id=record_id,
        user_id=10,
        payload={"expected_version": 1, "scope": "changed"},
        trace_id="trace-update",
    )
    assert updated["test_record"]["row_version"] == 2
    with pytest.raises(ApiError) as stale:
        service.update_test_record(
            record_id=record_id,
            user_id=10,
            payload={"expected_version": 1, "scope": "stale"},
            trace_id="trace-stale",
        )
    assert stale.value.code == "VERSION_CONFLICT"
    assert stale.value.details == [{"field": "row_version", "reason": "latest=2"}]

    submitted = service.submit_test_record(
        record_id=record_id,
        user_id=10,
        payload={"expected_version": 2},
        key="submit-key",
        trace_id="trace-submit",
    )
    replay = service.submit_test_record(
        record_id=record_id,
        user_id=10,
        payload={"expected_version": 2},
        key="submit-key",
        trace_id="trace-submit-replay",
    )
    assert replay == submitted
    assert submitted["test_record"]["status"] == "submitted"
    assert len(db.audit) == len(db.outbox) == 3
    for audit in db.audit:
        metadata = json.loads(audit["metadata"])
        assert metadata["schema_version"] == "test_record.mvp4.audit.v1"
        assert metadata["actual_role"] == "owner"
        assert "scope" not in json.dumps(metadata)
        assert "environment" not in json.dumps(metadata)
        assert "expected_result" not in json.dumps(metadata)
    assert all("scope" not in json.dumps(event, default=str) for event in db.outbox)

    with pytest.raises(ApiError) as immutable:
        service.update_test_record(
            record_id=record_id,
            user_id=10,
            payload={"expected_version": 3, "scope": "blocked"},
            trace_id="trace-immutable",
        )
    assert immutable.value.code == "TEST_RECORD_SUBMITTED"


def test_create_replay_precedes_fresh_source_guard(service_db):
    service, db = service_db
    first = service.create_test_record(
        round_id=3, user_id=10, payload=_payload(), key="replay-key", trace_id="trace-create"
    )
    before = (len(db.records), len(db.audit), len(db.outbox))
    db.round["status"] = "draft"
    replay = service.create_test_record(
        round_id=3, user_id=10, payload=_payload(), key="replay-key", trace_id="trace-replay"
    )
    assert replay == first
    assert (len(db.records), len(db.audit), len(db.outbox)) == before


def test_source_binding_mismatch_is_rejected_without_mutation(service_db):
    service, db = service_db
    db.plan_version["implementation_plan_id"] = 999
    before = copy.deepcopy(db.__dict__)
    with pytest.raises(ApiError) as mismatch:
        service.create_test_record(
            round_id=3, user_id=10, payload=_payload(), key="binding-key", trace_id="trace"
        )
    assert mismatch.value.code == "PLAN_VERSION_BINDING_MISMATCH"
    assert db.records == before["records"]
    assert db.audit == before["audit"]
    assert db.outbox == before["outbox"]


def test_outbox_failure_rolls_back_record_audit_and_idempotency(service_db):
    service, db = service_db
    db.fail_on_outbox = True
    with pytest.raises(RuntimeError):
        service.create_test_record(
            round_id=3, user_id=10, payload=_payload(), key="rollback-key", trace_id="trace"
        )
    assert db.records == []
    assert db.audit == []
    assert db.outbox == []
    assert db.idempotency == []


def test_write_lock_order_is_context_member_idempotency_source_record(service_db):
    service, db = service_db
    payload = _payload()

    service.create_test_record(
        round_id=3, user_id=10, payload=payload, key="order-create", trace_id="trace-create"
    )
    create_calls = db.calls
    source_context = next(i for i, sql in enumerate(create_calls) if sql.startswith("SELECT r.id AS round_id") and "FOR UPDATE" not in sql)
    member_lock = next(i for i, sql in enumerate(create_calls) if "SELECT role_code FROM project_member" in sql and "FOR UPDATE" in sql)
    idem = next(i for i, sql in enumerate(create_calls) if sql.startswith("INSERT IGNORE INTO idempotency_record"))
    source_lock = next(i for i, sql in enumerate(create_calls) if sql.startswith("SELECT r.id AS round_id") and "FOR UPDATE" in sql)
    assert source_context < member_lock < idem < source_lock

    db.calls.clear()
    record_id = int(db.records[0]["id"])
    service.update_test_record(
        record_id=record_id,
        user_id=10,
        payload={"expected_version": 1, "scope": "updated"},
        trace_id="trace-update",
    )
    update_calls = db.calls
    context = next(i for i, sql in enumerate(update_calls) if sql.startswith("SELECT tr.*") and "FOR UPDATE" not in sql)
    member_lock = next(i for i, sql in enumerate(update_calls) if "SELECT role_code FROM project_member" in sql and "FOR UPDATE" in sql)
    source_lock = next(i for i, sql in enumerate(update_calls) if sql.startswith("SELECT r.id AS round_id") and "FOR UPDATE" in sql)
    record_lock = next(i for i, sql in enumerate(update_calls) if sql.startswith("SELECT tr.*") and "FOR UPDATE" in sql)
    assert context < member_lock < source_lock < record_lock

    db.calls.clear()
    service.submit_test_record(
        record_id=record_id,
        user_id=10,
        payload={"expected_version": 2},
        key="order-submit",
        trace_id="trace-submit",
    )
    submit_calls = db.calls
    context = next(i for i, sql in enumerate(submit_calls) if sql.startswith("SELECT tr.*") and "FOR UPDATE" not in sql)
    member_lock = next(i for i, sql in enumerate(submit_calls) if "SELECT role_code FROM project_member" in sql and "FOR UPDATE" in sql)
    idem = next(i for i, sql in enumerate(submit_calls) if sql.startswith("INSERT IGNORE INTO idempotency_record"))
    source_lock = next(i for i, sql in enumerate(submit_calls) if sql.startswith("SELECT r.id AS round_id") and "FOR UPDATE" in sql)
    record_lock = next(i for i, sql in enumerate(submit_calls) if sql.startswith("SELECT tr.*") and "FOR UPDATE" in sql)
    assert context < member_lock < idem < source_lock < record_lock
