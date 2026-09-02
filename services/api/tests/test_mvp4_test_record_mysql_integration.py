from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.modules.confirmation.service import ConfirmationService
from app.platform.config import get_settings
from app.platform.database import get_engine

pytestmark = pytest.mark.integration


def _readiness() -> dict:
    return {
        "schema_version": "implementation_confirmation.readiness.mvp3.v1",
        "scope_status": "ready", "implementation_status": "ready",
        "configuration_status": "not_applicable", "data_change_status": "not_applicable",
        "known_blockers": [],
    }


def _content(label: str) -> dict:
    return {
        "schema_version": "implementation_plan.mvp3.v1",
        "features": [{"key": f"feature.{label}", "description": label}], "business_rules": [],
        "state_requirements": [], "exceptions": [], "interactions": [], "dependencies": [],
        "acceptance_scope": [{"key": f"acceptance.{label}", "description": label}],
    }


def _body(title: str = "MVP4 HTTP record") -> dict:
    return {"title": title, "scope": "", "environment": {"name": "", "preconditions": []},
            "steps": [], "expected_result": "", "actual_result": "", "result_status": "success"}


def _error(response) -> tuple[str, str]:
    payload = response.json()
    data = payload.get("error", payload)
    return str(data.get("code")), str(data.get("message", ""))


@pytest.mark.skipif(not os.getenv("MYSQL_TEST_DATABASE_URL"), reason="requires disposable MySQL")
def test_mvp4_test_record_real_http_mysql() -> None:
    url = os.environ["MYSQL_TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_engine.cache_clear(); get_settings.cache_clear()
    engine = get_engine()

    from app.main import app

    client = TestClient(app)
    password = "mvp4-pass"
    seed = uuid.uuid4().hex
    users: dict[str, dict] = {}

    def register(role: str) -> None:
        email = f"mvp4-{role}-{seed}@example.test"
        response = client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": role})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        users[role] = {"id": int(data["user"]["id"]), "token": data["access_token"]}

    try:
        with engine.connect() as connection:
            server = str(connection.execute(text("SELECT VERSION()")).scalar_one())
            head = str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
        assert re.match(r"^8\.4(?:\.|$)", server), server
        assert head == "20260823_0006", head
        for role in ("owner", "tester", "reviewer", "outsider"):
            register(role)
        now = datetime.now(UTC).replace(tzinfo=None)
        owner = users["owner"]["id"]
        tester = users["tester"]["id"]
        reviewer = users["reviewer"]["id"]
        with engine.begin() as connection:
            project = int(connection.execute(text(
                "INSERT INTO project (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,owner_user_id,name,description,status,last_module) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:u,:name,NULL,'active','product_design')"), {"n": now, "u": owner, "name": f"MVP4 {seed}"}).lastrowid)
            for uid, role in ((owner, "owner"), (tester, "tester"), (reviewer, "reviewer")):
                connection.execute(text(
                    "INSERT INTO project_member (created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) "
                    "VALUES (:n,:u,:n,:u,1,:p,:m,:r,'active')"), {"n": now, "u": owner, "p": project, "m": uid, "r": role})
            pv = int(connection.execute(text(
                "INSERT INTO project_version (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,workflow_node,is_working) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:p,NULL,'1','MVP4','integration','draft','product_design',1)"), {"n": now, "u": owner, "p": project}).lastrowid)
            req = int(connection.execute(text(
                "INSERT INTO requirement (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,title,source_type,priority,status,current_version_id) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:pv,:title,'manual','normal','confirmed',NULL)"), {"n": now, "u": owner, "pv": pv, "title": f"Requirement {seed}"}).lastrowid)
            reqv = int(connection.execute(text(
                "INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) "
                "VALUES (:n,:u,:r,NULL,'1','json','{}',:h,'confirmed',0,NULL,NULL,1)"), {"n": now, "u": owner, "r": req, "h": "a" * 64}).lastrowid)
            connection.execute(text("UPDATE requirement SET current_version_id=:v WHERE id=:r"), {"v": reqv, "r": req})
            prd = int(connection.execute(text(
                "INSERT INTO prd (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,source_requirement_version_id,name,prd_type,is_main,status,current_version_id) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:pv,:rv,'Source PRD','prd',1,'confirmed',NULL)"), {"n": now, "u": owner, "pv": pv, "rv": reqv}).lastrowid)
            prdv = int(connection.execute(text(
                "INSERT INTO prd_version (created_at,created_by,prd_id,source_version_id,version_no,content_format,content_json,content_hash,change_note,created_from_ai_result_id,is_effective) "
                "VALUES (:n,:u,:p,NULL,'1','json','{}',:h,'source',NULL,1)"), {"n": now, "u": owner, "p": prd, "h": "b" * 64}).lastrowid)
            connection.execute(text("UPDATE prd SET current_version_id=:v WHERE id=:p"), {"v": prdv, "p": prd})
            review = int(connection.execute(text(
                "INSERT INTO design_review (created_at,created_by,updated_at,updated_by,row_version,project_version_id,round_no,status,summary,submitted_at,passed_at,submitted_by,passed_by) "
                "VALUES (:n,:u,:n,:u,1,:pv,1,'passed','passed',:n,:n,:u,:u)"), {"n": now, "u": owner, "pv": pv}).lastrowid)
            for kind, obj, ver, h in (("PRD", prd, prdv, "b" * 64), ("REQUIREMENT", req, reqv, "a" * 64)):
                connection.execute(text(
                    "INSERT INTO design_review_scope (created_at,created_by,design_review_id,object_type,object_id,object_version_id,content_hash) VALUES (:n,:u,:r,:k,:o,:v,:h)"),
                    {"n": now, "u": owner, "r": review, "k": kind, "o": obj, "v": ver, "h": h})

        service = ConfirmationService()
        plan = service.create_plan(version_id=pv, user_id=owner, payload={"source_prd_version_id": str(prdv), "source_design_review_id": str(review), "name": "MVP4 Test Plan"}, key=f"plan-{seed}", trace_id=f"seed-{seed}")
        plan_id = int(plan["implementation_plan"]["id"])
        v1 = service.create_plan_version(plan_id=plan_id, user_id=owner, payload={"expected_version": 1, "content_json": _content(seed), "change_note": "integration"}, key=f"v1-{seed}", trace_id=f"seed-{seed}")
        v1_id = int(v1["implementation_plan_version"]["id"])
        service.set_effective(version_id=v1_id, user_id=owner, payload={"expected_version": 2}, key=f"eff-{seed}", trace_id=f"seed-{seed}")
        round_data = service.create_round(plan_id=plan_id, user_id=owner, payload={"plan_version_id": str(v1_id), "implementation_summary": "MVP4 disposable HTTP test confirmation round", "readiness_json": _readiness()}, key=f"round-{seed}", trace_id=f"seed-{seed}")
        round_id = int(round_data["confirmation_round"]["id"])
        service.confirm_round(round_id=round_id, user_id=owner, payload={"expected_version": 1}, key=f"confirm-{seed}", trace_id=f"seed-{seed}")
        auth = lambda role: {"Authorization": f"Bearer {users[role]['token']}"}

        empty = client.get(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers=auth("reviewer"))
        assert empty.status_code == 200 and empty.json()["data"]["items"] == []
        create_headers = {**auth("tester"), "Idempotency-Key": f"create-{seed}"}
        created = client.post(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers=create_headers, json=_body())
        assert created.status_code == 201, created.text
        record = created.json()["data"]["test_record"]
        record_id = record["id"]
        replay = client.post(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers=create_headers, json=_body())
        assert replay.status_code == 201 and replay.json()["data"]["test_record"]["id"] == record_id
        too_long = client.post(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers={**auth("tester"), "Idempotency-Key": f"long-{seed}"}, json=_body("x" * 201))
        assert too_long.status_code == 422
        reject_trace = f"reject-{seed}"
        incomplete_submit = client.post(f"/api/v1/test-records/{record_id}:submit", headers={**auth("tester"), "Idempotency-Key": f"bad-submit-{seed}", "X-Request-ID": reject_trace}, json={"expected_version": 1})
        assert incomplete_submit.status_code == 409 and _error(incomplete_submit)[0] == "TEST_RECORD_INCOMPLETE"
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM business_event_outbox WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id'))=:trace"), {"trace": reject_trace}).scalar_one() == 0
        complete = {"expected_version": 1, "scope": "scope", "environment": {"name": "MySQL 8.4.11", "preconditions": []}, "steps": ["run"], "expected_result": "ok", "actual_result": "ok", "result_status": "success"}
        patched = client.patch(f"/api/v1/test-records/{record_id}", headers=auth("tester"), json=complete)
        assert patched.status_code == 200 and patched.json()["data"]["test_record"]["row_version"] == 2
        stale = client.patch(f"/api/v1/test-records/{record_id}", headers=auth("tester"), json={**complete, "scope": "stale"})
        assert stale.status_code == 409 and _error(stale)[0] == "VERSION_CONFLICT" and "latest=2" in stale.text
        submitted = client.post(f"/api/v1/test-records/{record_id}:submit", headers={**auth("tester"), "Idempotency-Key": f"submit-{seed}"}, json={"expected_version": 2})
        assert submitted.status_code == 200 and submitted.json()["data"]["test_record"]["status"] == "submitted"
        submit_replay = client.post(f"/api/v1/test-records/{record_id}:submit", headers={**auth("tester"), "Idempotency-Key": f"submit-{seed}"}, json={"expected_version": 2})
        assert submit_replay.status_code == 200 and submit_replay.json()["data"]["test_record"] == submitted.json()["data"]["test_record"]
        resubmit = client.post(f"/api/v1/test-records/{record_id}:submit", headers={**auth("tester"), "Idempotency-Key": f"submit-new-{seed}"}, json={"expected_version": 3})
        assert resubmit.status_code == 409 and _error(resubmit)[0] == "TEST_RECORD_SUBMITTED"
        submitted_patch = client.patch(f"/api/v1/test-records/{record_id}", headers=auth("tester"), json={**complete, "expected_version": 3})
        assert submitted_patch.status_code == 409 and _error(submitted_patch)[0] == "TEST_RECORD_SUBMITTED"
        reopened = client.get(f"/api/v1/test-records/{record_id}", headers=auth("reviewer"))
        listed = client.get(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers=auth("reviewer"))
        assert reopened.status_code == listed.status_code == 200
        assert reopened.json()["data"]["test_record"] == listed.json()["data"]["items"][0]
        assert client.get(f"/api/v1/test-records/{record_id}", headers=auth("outsider")).status_code == 404
        assert client.post(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers={**auth("reviewer"), "Idempotency-Key": f"review-{seed}"}, json=_body()).status_code == 403

        second = client.post(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers={**auth("tester"), "Idempotency-Key": f"second-{seed}"}, json=_body("second"))
        assert second.status_code == 201
        second_id = second.json()["data"]["test_record"]["id"]
        with engine.begin() as connection:
            connection.execute(text("UPDATE confirmation_round SET status='superseded',confirm_status='superseded',is_effective=0 WHERE id=:id"), {"id": round_id})
        assert client.get(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers=auth("reviewer")).status_code == 200
        assert client.get(f"/api/v1/test-records/{second_id}", headers=auth("reviewer")).status_code == 200
        assert client.patch(f"/api/v1/test-records/{second_id}", headers=auth("tester"), json={**complete, "expected_version": 1}).status_code == 409
        assert client.post(f"/api/v1/test-records/{second_id}:submit", headers={**auth("tester"), "Idempotency-Key": f"historical-submit-{seed}"}, json={"expected_version": 1}).status_code == 409
        assert client.post(f"/api/v1/confirmation-rounds/{round_id}/test-records", headers={**auth("tester"), "Idempotency-Key": f"historical-create-{seed}"}, json=_body("third")).status_code == 409

        with engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM test_record WHERE confirmation_round_id=:r ORDER BY id"), {"r": round_id}).mappings().all()
            assert all(row["no_issue_conclusion"] == 0 and row["supersedes_test_record_id"] is None for row in rows)
            audit = connection.execute(text("SELECT operation_name,metadata_json FROM operation_audit_log WHERE object_type='test_record' AND object_id=:id"), {"id": int(record_id)}).mappings().all()
            assert {row["operation_name"] for row in audit} >= {"test.record.created", "test.record.draft.updated", "test.record.submitted"}
            for row in audit:
                metadata = json.loads(row["metadata_json"] or "{}")
                assert metadata.get("actual_role") in {"owner", "tester"}
                assert metadata.get("test_record_id") == int(record_id)
                assert not set(metadata) & {"title", "scope", "environment", "steps", "expected_result", "actual_result"}
            events = connection.execute(text("SELECT event_name,COUNT(*) FROM business_event_outbox WHERE aggregate_type='test_record' AND aggregate_id=:id GROUP BY event_name"), {"id": int(record_id)}).all()
            assert dict(events) == {"test.record.created": 1, "test.record.draft.updated": 1, "test.record.submitted": 1}
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        get_engine.cache_clear(); get_settings.cache_clear()
