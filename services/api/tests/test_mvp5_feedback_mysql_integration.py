from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.platform.config import get_settings
from app.platform.database import get_engine


pytestmark = pytest.mark.integration


def _error(response) -> str:
    payload = response.json()
    return str(payload.get("error", payload).get("code"))


@pytest.mark.skipif(not os.getenv("MYSQL_TEST_DATABASE_URL"), reason="requires disposable MySQL")
def test_mvp5_feedback_real_http_mysql_and_atomic_derived_version() -> None:
    url = os.environ["MYSQL_TEST_DATABASE_URL"]
    assert (make_url(url).database or "").endswith("_test")
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_engine.cache_clear()
    get_settings.cache_clear()
    engine = get_engine()
    from app.main import app

    client = TestClient(app)
    suffix = uuid.uuid4().hex
    password = "mvp5-pass"
    users: dict[str, dict[str, object]] = {}

    def register(role: str) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": f"mvp5-{role}-{suffix}@example.test", "password": password, "display_name": role},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        users[role] = {"id": int(data["user"]["id"]), "token": data["access_token"]}

    def auth(role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {users[role]['token']}"}

    try:
        with engine.connect() as connection:
            assert re.match(r"^8\.4(?:\.|$)", str(connection.execute(text("SELECT VERSION()" )).scalar_one()))
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260823_0006"
        for role in ("owner", "tester", "reviewer"):
            register(role)
        owner, tester, reviewer = (int(users[role]["id"]) for role in ("owner", "tester", "reviewer"))
        now = datetime.now(UTC).replace(tzinfo=None)
        with engine.begin() as connection:
            project = int(connection.execute(text(
                "INSERT INTO project (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,owner_user_id,name,description,status,last_module) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:u,:name,NULL,'active','validation')"
            ), {"n": now, "u": owner, "name": f"MVP5 {suffix}"}).lastrowid)
            for user_id, role in ((owner, "owner"), (tester, "tester"), (reviewer, "reviewer")):
                connection.execute(text(
                    "INSERT INTO project_member (created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) "
                    "VALUES (:n,:u,:n,:u,1,:p,:member,:role,'active')"
                ), {"n": now, "u": owner, "p": project, "member": user_id, "role": role})
            version = int(connection.execute(text(
                "INSERT INTO project_version (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,workflow_node,is_working) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:p,NULL,'V1','V1','fixture','active','validation',1)"
            ), {"n": now, "u": owner, "p": project}).lastrowid)
            requirement = int(connection.execute(text(
                "INSERT INTO requirement (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,title,source_type,priority,status,current_version_id) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:v,'Fixture requirement','manual','normal','confirmed',NULL)"
            ), {"n": now, "u": owner, "v": version}).lastrowid)
            requirement_version = int(connection.execute(text(
                "INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) "
                "VALUES (:n,:u,:r,NULL,'1','json','{}',:hash,'confirmed',0,NULL,NULL,1)"
            ), {"n": now, "u": owner, "r": requirement, "hash": "b" * 64}).lastrowid)
            connection.execute(text("UPDATE requirement SET current_version_id=:rv WHERE id=:r"), {"rv": requirement_version, "r": requirement})
            prd = int(connection.execute(text(
                "INSERT INTO prd (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,source_requirement_version_id,name,prd_type,is_main,status,current_version_id) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:v,:rv,'Fixture PRD','prd',1,'confirmed',NULL)"
            ), {"n": now, "u": owner, "v": version, "rv": requirement_version}).lastrowid)
            prd_version = int(connection.execute(text(
                "INSERT INTO prd_version (created_at,created_by,prd_id,source_version_id,version_no,content_format,content_json,content_hash,change_note,created_from_ai_result_id,is_effective) "
                "VALUES (:n,:u,:p,NULL,'1','json','{}',:hash,'fixture',NULL,1)"
            ), {"n": now, "u": owner, "p": prd, "hash": "c" * 64}).lastrowid)
            connection.execute(text("UPDATE prd SET current_version_id=:pv WHERE id=:p"), {"pv": prd_version, "p": prd})
            review = int(connection.execute(text(
                "INSERT INTO design_review (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,round_no,status,summary,submitted_at,passed_at,submitted_by,passed_by) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:v,1,'passed','fixture',:n,:n,:u,:u)"
            ), {"n": now, "u": owner, "v": version}).lastrowid)
            plan = int(connection.execute(text(
                "INSERT INTO implementation_plan (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,name,status,current_version_id,source_prd_version_id,source_design_review_id) "
                "VALUES (:n,:u,:n,:u,1,NULL,NULL,:v,'MVP5 fixture','active',NULL,:prd,:review)"
            ), {"n": now, "u": owner, "v": version, "prd": prd_version, "review": review}).lastrowid)
            plan_version = int(connection.execute(text(
                "INSERT INTO implementation_plan_version (created_at,created_by,implementation_plan_id,source_version_id,version_no,review_id,content_json,content_hash,change_note,created_from_ai_result_id,is_effective) "
                "VALUES (:n,:u,:p,NULL,'1',:review,'{}',:hash,'fixture',NULL,1)"
            ), {"n": now, "u": owner, "p": plan, "review": review, "hash": "a" * 64}).lastrowid)
            connection.execute(text("UPDATE implementation_plan SET current_version_id=:pv WHERE id=:p"), {"pv": plan_version, "p": plan})
            round_id = int(connection.execute(text(
                "INSERT INTO confirmation_round (created_at,created_by,updated_at,updated_by,row_version,implementation_plan_id,plan_version_id,round_no,status,confirm_status,is_effective,confirmed_by,confirmed_at,superseded_at,source_round_id,implementation_summary,readiness_json) "
                "VALUES (:n,:u,:n,:u,1,:p,:pv,1,'confirmed','confirmed',1,:u,:n,NULL,NULL,'fixture','{}')"
            ), {"n": now, "u": owner, "p": plan, "pv": plan_version}).lastrowid)

            def test_record(title: str) -> int:
                return int(connection.execute(text(
                    "INSERT INTO test_record (created_at,created_by,updated_at,updated_by,row_version,confirmation_round_id,supersedes_test_record_id,title,test_type,scope,environment_json,steps_json,expected_result,actual_result,result_status,no_issue_conclusion,tester_id,submitted_at) "
                    "VALUES (:n,:t,:n,:t,1,:r,NULL,:title,'manual','scope','{}','[\"run\"]','ok','ok','success',0,:t,:n)"
                ), {"n": now, "t": tester, "r": round_id, "title": title}).lastrowid)

            no_issue_record = test_record("no issue")
            defect_record = test_record("defect")
            optimization_record = test_record("optimization")

        conclusion_headers = {**auth("tester"), "Idempotency-Key": f"conclude-{suffix}"}
        concluded = client.post(f"/api/v1/test-records/{no_issue_record}:conclude-no-issue", headers=conclusion_headers, json={"expected_version": 1})
        assert concluded.status_code == 200, concluded.text
        assert concluded.json()["data"]["test_record"]["no_issue_conclusion"] is True
        replay = client.post(f"/api/v1/test-records/{no_issue_record}:conclude-no-issue", headers=conclusion_headers, json={"expected_version": 1})
        assert replay.status_code == 200 and replay.json()["data"] == concluded.json()["data"]

        defect = {
            "test_record_id": str(defect_record), "issue_type": "defect", "title": "submit fails", "description": "fixture",
            "priority": "high", "severity": "high", "assignee_id": str(tester),
            "bug_detail": {"reproduce_steps": "run", "expected_result": "ok", "actual_result": "error", "environment": {"name": "mysql"}},
            "optimization_detail": None,
        }
        create_headers = {**auth("tester"), "Idempotency-Key": f"issue-{suffix}"}
        created = client.post(f"/api/v1/project-versions/{version}/issues", headers=create_headers, json=defect)
        assert created.status_code == 201, created.text
        issue = created.json()["data"]["issue"]
        create_replay = client.post(f"/api/v1/project-versions/{version}/issues", headers=create_headers, json=defect)
        assert create_replay.status_code == 201 and create_replay.json()["data"] == created.json()["data"]
        conflict = client.post(f"/api/v1/test-records/{defect_record}:conclude-no-issue", headers={**auth("tester"), "Idempotency-Key": f"conflict-{suffix}"}, json={"expected_version": 1})
        assert conflict.status_code == 409 and _error(conflict) == "TEST_RECORD_HAS_ISSUES"
        forbidden = client.patch(f"/api/v1/issues/{issue['id']}", headers={**auth("reviewer"), "Idempotency-Key": f"reviewer-{suffix}"}, json={"expected_version": 1, "title": "blocked"})
        assert forbidden.status_code == 403
        update_headers = {**auth("tester"), "Idempotency-Key": f"update-{suffix}"}
        updated = client.patch(f"/api/v1/issues/{issue['id']}", headers=update_headers, json={"expected_version": 1, "title": "submit still fails"})
        assert updated.status_code == 200 and updated.json()["data"]["issue"]["row_version"] == 2
        update_replay = client.patch(f"/api/v1/issues/{issue['id']}", headers=update_headers, json={"expected_version": 1, "title": "submit still fails"})
        assert update_replay.status_code == 200 and update_replay.json()["data"] == updated.json()["data"]
        disposition = client.post(f"/api/v1/issues/{issue['id']}/dispositions", headers={**auth("owner"), "Idempotency-Key": f"dispose-{suffix}"}, json={"expected_version": 2, "disposition_type": "current_version_fix", "reason": "fix locally", "responsible_user_id": str(tester)})
        assert disposition.status_code == 200 and disposition.json()["data"]["issue"]["status"] == "routed_current_fix"

        optimization = {
            "test_record_id": str(optimization_record), "issue_type": "optimization", "title": "reduce steps", "description": "fixture",
            "priority": "medium", "severity": "low", "assignee_id": None, "bug_detail": None,
            "optimization_detail": {"problem_evidence": "three steps", "hypothesis": "combine", "expected_outcome": "one step", "impact_scope": "editor", "need_new_version": True},
        }
        optimization_response = client.post(f"/api/v1/project-versions/{version}/issues", headers={**auth("tester"), "Idempotency-Key": f"optimization-{suffix}"}, json=optimization)
        assert optimization_response.status_code == 201, optimization_response.text
        optimization_issue = optimization_response.json()["data"]["issue"]
        derived = client.post(f"/api/v1/projects/{project}/versions:derive", headers={**auth("owner"), "Idempotency-Key": f"derive-{suffix}"}, json={
            "source_version_id": str(version), "source_issue_id": optimization_issue["id"], "change_type": "optimization", "change_reason": "route optimization",
            "inheritance_choices": {"requirements": True, "prd": True, "implementation_plan": False}, "expected_project_version": 1,
        })
        assert derived.status_code == 200, derived.text
        derived_version = derived.json()["data"]
        assert derived_version["is_working"] is False and derived_version["parent_version_id"] == str(version)
        refreshed = client.get(f"/api/v1/issues/{optimization_issue['id']}", headers=auth("reviewer"))
        assert refreshed.status_code == 200
        refreshed_issue = refreshed.json()["data"]["issue"]
        assert refreshed_issue["status"] == "routed_new_version"
        assert refreshed_issue["dispositions"][0]["target_project_version_id"] == derived_version["id"]

        with engine.connect() as connection:
            change = connection.execute(text("SELECT source_issue_id,to_version_id FROM version_change_record WHERE source_issue_id=:issue"), {"issue": int(optimization_issue["id"])}).mappings().one()
            assert int(change["to_version_id"]) == int(derived_version["id"])
            assert connection.execute(text("SELECT is_working FROM project_version WHERE id=:id"), {"id": int(derived_version["id"])}).scalar_one() == 0
            event_names = {row[0] for row in connection.execute(text("SELECT event_name FROM business_event_outbox WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.project_id'))=:project"), {"project": str(project)}).all()}
            assert {"test.record.validation_completed", "issue.created", "issue.updated", "issue.disposition.created", "project.version.derived"} <= event_names
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        get_engine.cache_clear()
        get_settings.cache_clear()
