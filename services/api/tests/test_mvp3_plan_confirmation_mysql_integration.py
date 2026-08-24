from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.modules.confirmation.service import ConfirmationService
from app.platform.config import get_settings
from app.platform.database import get_engine
from app.platform.errors import ApiError

pytestmark = pytest.mark.integration


def _content(label: str) -> dict:
    return {
        "schema_version": "implementation_plan.mvp3.v1",
        "features": [{"key": f"feature.{label}", "description": f"Feature scope {label}"}],
        "business_rules": [],
        "state_requirements": [],
        "exceptions": [],
        "interactions": [],
        "dependencies": [],
        "acceptance_scope": [
            {"key": f"acceptance.{label}", "description": f"Acceptance scope {label}"}
        ],
    }


def _readiness() -> dict:
    return {
        "schema_version": "implementation_confirmation.readiness.mvp3.v1",
        "scope_status": "ready",
        "implementation_status": "ready",
        "configuration_status": "not_applicable",
        "data_change_status": "not_applicable",
        "known_blockers": [],
    }


@pytest.mark.skipif(
    not os.getenv("MYSQL_TEST_DATABASE_URL"),
    reason="requires approved disposable MySQL 8.4 database",
)
def test_mvp3_mysql_main_chain_and_reconfirmation() -> None:
    test_url = os.environ["MYSQL_TEST_DATABASE_URL"]
    if not (make_url(test_url).database or "").endswith("_test"):
        raise AssertionError("MVP3 integration requires a dedicated *_test database")
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_url
    get_engine.cache_clear()
    get_settings.cache_clear()
    engine = get_engine()
    token = f"mvp3_{uuid.uuid4().hex}"
    now = datetime.now(UTC).replace(tzinfo=None)
    user_id = reader_id = project_id = project_version_id = requirement_id = (
        requirement_version_id
    ) = prd_id = prd_version_id = review_id = 0
    plan_id = version_1_id = version_2_id = round_1_id = 0
    service = ConfirmationService()
    try:
        with engine.connect() as connection:
            server = str(connection.execute(text("SELECT VERSION()")).scalar_one())
            head = str(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            )
        if re.match(r"^8\.4(?:\.|$)", server) is None or head != "20260823_0006":
            raise AssertionError(
                "MVP3 integration requires MySQL 8.4 and Alembic 20260823_0006, "
                f"got {server}/{head}"
            )
        with engine.begin() as connection:
            user_id = int(
                connection.execute(
                    text(
                        "INSERT INTO user_account "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,email,password_hash,display_name,system_role,status,"
                        "last_login_at) "
                        "VALUES (:now,NULL,:now,NULL,1,NULL,NULL,:email,'placeholder',:name,"
                        "'user','active',NULL)"
                    ),
                    {"now": now, "email": f"{token}@example.test", "name": token},
                ).lastrowid
            )
            reader_id = int(
                connection.execute(
                    text(
                        "INSERT INTO user_account "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,email,password_hash,display_name,system_role,status,"
                        "last_login_at) "
                        "VALUES (:now,NULL,:now,NULL,1,NULL,NULL,:email,'placeholder',:name,"
                        "'user','active',NULL)"
                    ),
                    {
                        "now": now,
                        "email": f"reader-{token}@example.test",
                        "name": f"reader-{token}",
                    },
                ).lastrowid
            )
            project_id = int(
                connection.execute(
                    text(
                        "INSERT INTO project "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,owner_user_id,name,description,status,last_module) "
                        "VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:uid,:name,NULL,'active',"
                        "'product_design')"
                    ),
                    {"now": now, "uid": user_id, "name": token},
                ).lastrowid
            )
            connection.execute(
                text(
                    "INSERT INTO project_member "
                    "(created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,"
                    "role_code,status) VALUES (:now,:uid,:now,:uid,1,:project,:uid,'owner',"
                    "'active')"
                ),
                {"now": now, "uid": user_id, "project": project_id},
            )
            connection.execute(
                text(
                    "INSERT INTO project_member "
                    "(created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,"
                    "role_code,status) VALUES (:now,:uid,:now,:uid,1,:project,:reader,"
                    "'implementer','active')"
                ),
                {"now": now, "uid": user_id, "reader": reader_id, "project": project_id},
            )
            project_version_id = int(
                connection.execute(
                    text(
                        "INSERT INTO project_version "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,project_id,parent_version_id,version_no,version_name,"
                        "creation_reason,lifecycle_status,workflow_node,is_working) "
                        "VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:project,NULL,'1','MVP3',"
                        "'integration','draft','product_design',1)"
                    ),
                    {"now": now, "uid": user_id, "project": project_id},
                ).lastrowid
            )
            requirement_id = int(
                connection.execute(
                    text(
                        "INSERT INTO requirement "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,project_version_id,title,source_type,priority,status,"
                        "current_version_id) VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:version,"
                        ":title,'manual','normal','confirmed',NULL)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "version": project_version_id,
                        "title": f"Requirement {token}",
                    },
                ).lastrowid
            )
            requirement_version_id = int(
                connection.execute(
                    text(
                        "INSERT INTO requirement_version "
                        "(created_at,created_by,requirement_id,source_version_id,version_no,"
                        "content_format,content_json,content_hash,confirmation_status,"
                        "unresolved_count,risk_acceptance_json,created_from_ai_result_id,"
                        "is_effective) "
                        "VALUES (:now,:uid,:requirement,NULL,'1','json','{}',:hash,"
                        "'confirmed',0,NULL,NULL,1)"
                    ),
                    {"now": now, "uid": user_id, "requirement": requirement_id, "hash": "b" * 64},
                ).lastrowid
            )
            connection.execute(
                text("UPDATE requirement SET current_version_id=:version WHERE id=:requirement"),
                {"version": requirement_version_id, "requirement": requirement_id},
            )
            prd_id = int(
                connection.execute(
                    text(
                        "INSERT INTO prd "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,"
                        "archived_by,project_version_id,source_requirement_version_id,name,"
                        "prd_type,is_main,status,current_version_id) "
                        "VALUES (:now,:uid,:now,:uid,1,NULL,NULL,:version,:source,"
                        "'Source PRD','prd',1,'confirmed',NULL)"
                    ),
                    {
                        "now": now,
                        "uid": user_id,
                        "version": project_version_id,
                        "source": requirement_version_id,
                    },
                ).lastrowid
            )
            prd_version_id = int(
                connection.execute(
                    text(
                        "INSERT INTO prd_version "
                        "(created_at,created_by,prd_id,source_version_id,version_no,content_format,"
                        "content_json,content_hash,change_note,created_from_ai_result_id,"
                        "is_effective) "
                        "VALUES (:now,:uid,:prd,NULL,'1','json','{}',:hash,'source',NULL,1)"
                    ),
                    {"now": now, "uid": user_id, "prd": prd_id, "hash": "a" * 64},
                ).lastrowid
            )
            connection.execute(
                text("UPDATE prd SET current_version_id=:version WHERE id=:prd"),
                {"version": prd_version_id, "prd": prd_id},
            )
            review_id = int(
                connection.execute(
                    text(
                        "INSERT INTO design_review "
                        "(created_at,created_by,updated_at,updated_by,row_version,project_version_id,"
                        "round_no,status,summary,submitted_at,passed_at,submitted_by,passed_by) "
                        "VALUES (:now,:uid,:now,:uid,1,:version,1,'passed','passed',"
                        ":now,:now,:uid,:uid)"
                    ),
                    {"now": now, "uid": user_id, "version": project_version_id},
                ).lastrowid
            )
            connection.execute(
                text(
                    "INSERT INTO design_review_scope "
                    "(created_at,created_by,design_review_id,object_type,object_id,"
                    "object_version_id,content_hash) VALUES (:now,:uid,:review,'PRD',"
                    ":prd,:version,:hash)"
                ),
                {
                    "now": now,
                    "uid": user_id,
                    "review": review_id,
                    "prd": prd_id,
                    "version": prd_version_id,
                    "hash": "a" * 64,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO design_review_scope "
                    "(created_at,created_by,design_review_id,object_type,object_id,"
                    "object_version_id,content_hash) VALUES (:now,:uid,:review,'REQUIREMENT',"
                    ":object_id,:version,:hash)"
                ),
                {
                    "now": now,
                    "uid": user_id,
                    "review": review_id,
                    "object_id": requirement_id,
                    "version": requirement_version_id,
                    "hash": "b" * 64,
                },
            )
        created = service.create_plan(
            version_id=project_version_id,
            user_id=user_id,
            payload={
                "source_prd_version_id": str(prd_version_id),
                "source_design_review_id": str(review_id),
                "name": "Implementation Plan",
            },
            key=f"create-{token}",
            trace_id=f"trace-{token}",
        )
        plan_id = int(created["implementation_plan"]["id"])
        with engine.connect() as connection:
            command_ids = (
                connection.execute(
                    text(
                        "SELECT command_id FROM operation_audit_log "
                        "WHERE object_type='implementation_plan' AND object_id=:plan "
                        "AND trace_id=:trace"
                    ),
                    {"plan": plan_id, "trace": f"trace-{token}"},
                )
                .scalars()
                .all()
            )
            assert command_ids
            assert all(
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM business_event_outbox "
                        "WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.command_id'))=:command"
                    ),
                    {"command": command_id},
                ).scalar_one()
                == 1
                for command_id in command_ids
            )
        replay = service.create_plan(
            version_id=project_version_id,
            user_id=user_id,
            payload={
                "source_prd_version_id": str(prd_version_id),
                "source_design_review_id": str(review_id),
                "name": "Implementation Plan",
            },
            key=f"create-{token}",
            trace_id=f"trace-replay-{token}",
        )
        assert replay["implementation_plan"]["id"] == str(plan_id)
        saved_1 = service.create_plan_version(
            plan_id=plan_id,
            user_id=user_id,
            payload={
                "expected_version": 1,
                "content_json": _content("one"),
                "change_note": "Initial implementation scope",
            },
            key=f"v1-{token}",
            trace_id=f"trace-{token}",
        )
        version_1_id = int(saved_1["implementation_plan_version"]["id"])
        assert saved_1["implementation_plan_version"]["source_version_id"] is None
        effective_1 = service.set_effective(
            version_id=version_1_id,
            user_id=user_id,
            payload={"expected_version": 2},
            key=f"effective-1-{token}",
            trace_id=f"trace-{token}",
        )
        round_1 = service.create_round(
            plan_id=plan_id,
            user_id=reader_id,
            payload={
                "plan_version_id": str(version_1_id),
                "implementation_summary": "A human implementation scope for version one.",
                "readiness_json": _readiness(),
            },
            key=f"round-1-{token}",
            trace_id=f"trace-{token}",
        )
        round_1_id = int(round_1["confirmation_round"]["id"])
        updated_round_1 = service.update_round(
            round_id=round_1_id,
            user_id=reader_id,
            payload={
                "expected_version": 1,
                "plan_version_id": str(version_1_id),
                "implementation_summary": "Updated human implementation scope for version one.",
                "readiness_json": _readiness(),
            },
            trace_id=f"trace-{token}",
        )
        assert updated_round_1["confirmation_round"]["row_version"] == 2
        with engine.connect() as connection:
            update_commands = (
                connection.execute(
                    text(
                        "SELECT command_id FROM operation_audit_log "
                        "WHERE operation_name='confirmation_round.draft.updated' "
                        "AND object_id=:round AND trace_id=:trace"
                    ),
                    {"round": round_1_id, "trace": f"trace-{token}"},
                )
                .scalars()
                .all()
            )
            assert len(update_commands) == 1
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM business_event_outbox "
                        "WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.command_id'))=:command"
                    ),
                    {"command": update_commands[0]},
                ).scalar_one()
                == 1
            )
        stale_round_before = service.get_round(round_id=round_1_id, user_id=user_id)
        with pytest.raises(ApiError) as stale_round:
            service.update_round(
                round_id=round_1_id,
                user_id=reader_id,
                payload={
                    "expected_version": 1,
                    "plan_version_id": str(version_1_id),
                    "implementation_summary": "A stale human implementation scope.",
                    "readiness_json": _readiness(),
                },
                trace_id=f"trace-{token}",
            )
        assert stale_round.value.code == "VERSION_CONFLICT"
        assert service.get_round(round_id=round_1_id, user_id=user_id) == stale_round_before
        with pytest.raises(ApiError) as implementer_confirm:
            service.confirm_round(
                round_id=round_1_id,
                user_id=reader_id,
                payload={"expected_version": 2},
                key=f"confirm-1-implementer-{token}",
                trace_id=f"trace-{token}",
            )
        assert implementer_confirm.value.code == "FORBIDDEN"
        confirmed_1 = service.confirm_round(
            round_id=round_1_id,
            user_id=user_id,
            payload={"expected_version": 2},
            key=f"confirm-1-{token}",
            trace_id=f"trace-{token}",
        )
        with pytest.raises(ApiError) as stale_version:
            service.create_plan_version(
                plan_id=plan_id,
                user_id=user_id,
                payload={
                    "expected_version": 1,
                    "content_json": _content("stale"),
                    "change_note": "Stale implementation scope",
                },
                key=f"stale-version-{token}",
                trace_id=f"trace-{token}",
            )
        assert stale_version.value.code == "VERSION_CONFLICT"
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE prd SET archived_at=:now,archived_by=:uid WHERE id=:id"),
                {"now": now, "uid": user_id, "id": prd_id},
            )
        saved_2 = service.create_plan_version(
            plan_id=plan_id,
            user_id=user_id,
            payload={
                "expected_version": 3,
                "content_json": _content("two"),
                "change_note": "Second implementation scope",
            },
            key=f"v2-{token}",
            trace_id=f"trace-{token}",
        )
        version_2_id = int(saved_2["implementation_plan_version"]["id"])
        assert saved_2["implementation_plan_version"]["source_version_id"] == str(version_1_id)
        with pytest.raises(ApiError) as archived_source:
            service.set_effective(
                version_id=version_2_id,
                user_id=user_id,
                payload={"expected_version": 4},
                key=f"effective-2-blocked-{token}",
                trace_id=f"trace-{token}",
            )
        assert archived_source.value.code == "SOURCE_PRD_NOT_CONFIRMED"
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE prd SET archived_at=NULL,archived_by=NULL WHERE id=:id"),
                {"id": prd_id},
            )
            connection.execute(
                text("UPDATE design_review SET archived_at=:now WHERE id=:id"),
                {"now": now, "id": review_id},
            )
        with pytest.raises(ApiError) as archived_review:
            service.set_effective(
                version_id=version_2_id,
                user_id=user_id,
                payload={"expected_version": 4},
                key=f"effective-2-review-blocked-{token}",
                trace_id=f"trace-{token}",
            )
        assert archived_review.value.code == "SOURCE_REVIEW_NOT_PASSED"
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE design_review SET archived_at=NULL WHERE id=:id"), {"id": review_id}
            )
        service.set_effective(
            version_id=version_2_id,
            user_id=user_id,
            payload={"expected_version": 4},
            key=f"effective-2-{token}",
            trace_id=f"trace-{token}",
        )
        assert (
            service.get_plan(plan_id=plan_id, user_id=reader_id)["implementation_plan"][
                "confirmation_state"
            ]
            == "needs_reconfirmation"
        )
        round_2 = service.create_round(
            plan_id=plan_id,
            user_id=reader_id,
            payload={
                "plan_version_id": str(version_2_id),
                "implementation_summary": "A human implementation scope for version two.",
                "readiness_json": _readiness(),
            },
            key=f"round-2-{token}",
            trace_id=f"trace-{token}",
        )
        round_2_id = int(round_2["confirmation_round"]["id"])
        confirmed = service.confirm_round(
            round_id=round_2_id,
            user_id=user_id,
            payload={"expected_version": 1},
            key=f"confirm-2-{token}",
            trace_id=f"trace-{token}",
        )
        assert confirmed["confirmation_round"]["status"] == "confirmed"
        for role in ("reviewer", "tester"):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE project_member SET role_code=:role "
                        "WHERE project_id=:project AND user_id=:user"
                    ),
                    {"role": role, "project": project_id, "user": reader_id},
                )
            assert service.get_plan(plan_id=plan_id, user_id=reader_id)["implementation_plan"][
                "id"
            ] == str(plan_id)
            assert len(service.list_rounds(plan_id=plan_id, user_id=reader_id)["items"]) == 2
            with pytest.raises(ApiError) as forbidden_write:
                service.create_round(
                    plan_id=plan_id,
                    user_id=reader_id,
                    payload={
                        "plan_version_id": str(version_2_id),
                        "implementation_summary": "A forbidden implementation scope.",
                        "readiness_json": _readiness(),
                    },
                    key=f"forbidden-{role}-{token}",
                    trace_id=f"trace-{token}",
                )
            assert forbidden_write.value.code == "FORBIDDEN"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE project_member SET role_code='implementer' "
                    "WHERE project_id=:project AND user_id=:user"
                ),
                {"project": project_id, "user": reader_id},
            )
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE project_version SET archived_at=:now,archived_by=:uid WHERE id=:id"),
                {"now": now, "uid": user_id, "id": project_version_id},
            )
        try:
            with pytest.raises(ApiError) as archived_project_version:
                service.get_plan(plan_id=plan_id, user_id=reader_id)
            assert archived_project_version.value.code == "NOT_FOUND"
        finally:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE project_version SET archived_at=NULL,archived_by=NULL WHERE id=:id"
                    ),
                    {"id": project_version_id},
                )
        before_replays = {}
        with engine.connect() as connection:
            before_replays["plans"] = connection.execute(
                text("SELECT COUNT(*) FROM implementation_plan WHERE id=:id"), {"id": plan_id}
            ).scalar_one()
            before_replays["versions"] = connection.execute(
                text(
                    "SELECT COUNT(*) FROM implementation_plan_version "
                    "WHERE implementation_plan_id=:id"
                ),
                {"id": plan_id},
            ).scalar_one()
            before_replays["rounds"] = connection.execute(
                text("SELECT COUNT(*) FROM confirmation_round WHERE implementation_plan_id=:id"),
                {"id": plan_id},
            ).scalar_one()
            before_replays["audits"] = connection.execute(
                text("SELECT COUNT(*) FROM operation_audit_log WHERE trace_id LIKE :trace"),
                {"trace": f"trace-{token}%"},
            ).scalar_one()
            before_replays["outbox"] = connection.execute(
                text(
                    "SELECT COUNT(*) FROM business_event_outbox "
                    "WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id')) LIKE :trace"
                ),
                {"trace": f"trace-{token}%"},
            ).scalar_one()
            before_replays["idempotency"] = connection.execute(
                text("SELECT COUNT(*) FROM idempotency_record WHERE user_id IN (:owner,:reader)"),
                {"owner": user_id, "reader": reader_id},
            ).scalar_one()
        assert (
            service.create_plan(
                version_id=project_version_id,
                user_id=user_id,
                payload={
                    "source_prd_version_id": str(prd_version_id),
                    "source_design_review_id": str(review_id),
                    "name": "Implementation Plan",
                },
                key=f"create-{token}",
                trace_id=f"trace-late-replay-{token}",
            )
            == created
        )
        assert (
            service.create_plan_version(
                plan_id=plan_id,
                user_id=user_id,
                payload={
                    "expected_version": 1,
                    "content_json": _content("one"),
                    "change_note": "Initial implementation scope",
                },
                key=f"v1-{token}",
                trace_id=f"trace-late-replay-{token}",
            )
            == saved_1
        )
        assert (
            service.set_effective(
                version_id=version_1_id,
                user_id=user_id,
                payload={"expected_version": 2},
                key=f"effective-1-{token}",
                trace_id=f"trace-late-replay-{token}",
            )
            == effective_1
        )
        assert (
            service.confirm_round(
                round_id=round_1_id,
                user_id=user_id,
                payload={"expected_version": 2},
                key=f"confirm-1-{token}",
                trace_id=f"trace-late-replay-{token}",
            )
            == confirmed_1
        )
        late_round_replay = service.create_round(
            plan_id=plan_id,
            user_id=reader_id,
            payload={
                "plan_version_id": str(version_1_id),
                "implementation_summary": "A human implementation scope for version one.",
                "readiness_json": _readiness(),
            },
            key=f"round-1-{token}",
            trace_id=f"trace-late-replay-{token}",
        )
        assert late_round_replay == round_1
        assert late_round_replay["confirmation_round"]["row_version"] == 1
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM implementation_plan WHERE id=:id"), {"id": plan_id}
                ).scalar_one()
                == before_replays["plans"]
            )
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM implementation_plan_version "
                        "WHERE implementation_plan_id=:id"
                    ),
                    {"id": plan_id},
                ).scalar_one()
                == before_replays["versions"]
            )
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM confirmation_round WHERE implementation_plan_id=:id"
                    ),
                    {"id": plan_id},
                ).scalar_one()
                == before_replays["rounds"]
            )
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM operation_audit_log WHERE trace_id LIKE :trace"),
                    {"trace": f"trace-{token}%"},
                ).scalar_one()
                == before_replays["audits"]
            )
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM business_event_outbox "
                        "WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id')) LIKE :trace"
                    ),
                    {"trace": f"trace-{token}%"},
                ).scalar_one()
                == before_replays["outbox"]
            )
            assert (
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM idempotency_record WHERE user_id IN (:owner,:reader)"
                    ),
                    {"owner": user_id, "reader": reader_id},
                ).scalar_one()
                == before_replays["idempotency"]
            )
        with pytest.raises(ApiError) as conflict:
            service.create_plan(
                version_id=project_version_id,
                user_id=user_id,
                payload={
                    "source_prd_version_id": str(prd_version_id),
                    "source_design_review_id": str(review_id),
                    "name": "Different Plan",
                },
                key=f"create-{token}",
                trace_id=f"trace-late-conflict-{token}",
            )
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
        bad_round = service.create_round(
            plan_id=plan_id,
            user_id=user_id,
            payload={
                "plan_version_id": str(version_2_id),
                "implementation_summary": "A human implementation scope for a blocked round.",
                "readiness_json": {**_readiness(), "known_blockers": ["not ready"]},
            },
            key=f"round-bad-{token}",
            trace_id=f"trace-{token}",
        )
        before_bad = service.get_round(
            round_id=int(bad_round["confirmation_round"]["id"]), user_id=user_id
        )
        with pytest.raises(ApiError) as readiness_error:
            service.confirm_round(
                round_id=int(bad_round["confirmation_round"]["id"]),
                user_id=user_id,
                payload={"expected_version": 1},
                key=f"confirm-bad-{token}",
                trace_id=f"trace-{token}",
            )
        assert readiness_error.value.code == "READINESS_INCOMPLETE"
        assert (
            service.get_round(round_id=int(bad_round["confirmation_round"]["id"]), user_id=user_id)
            == before_bad
        )
        with pytest.raises(ApiError) as duplicate_draft:
            service.create_round(
                plan_id=plan_id,
                user_id=user_id,
                payload={
                    "plan_version_id": str(version_2_id),
                    "implementation_summary": "A second draft that must be rejected.",
                    "readiness_json": _readiness(),
                },
                key=f"round-duplicate-{token}",
                trace_id=f"trace-{token}",
            )
        assert duplicate_draft.value.code == "CONFIRMATION_ALREADY_EXISTS"
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT id,status,is_effective,source_round_id FROM confirmation_round "
                    "WHERE implementation_plan_id=:plan ORDER BY round_no"
                ),
                {"plan": plan_id},
            ).all()
            history = [
                (row.status, row.is_effective)
                for row in rows
                if row.status in {"confirmed", "superseded"}
            ]
            assert history == [("superseded", 0), ("confirmed", 1)]
            drafts = [row for row in rows if row.status == "draft"]
            assert len(drafts) == 1 and drafts[0].is_effective == 0
            assert rows[1].source_round_id == round_1_id
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM business_event_outbox "
                    "WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id')) LIKE :trace"
                ),
                {"trace": f"trace-{token}%"},
            )
            connection.execute(
                text("DELETE FROM operation_audit_log WHERE trace_id LIKE :trace"),
                {"trace": f"trace-{token}%"},
            )
            if plan_id:
                connection.execute(
                    text("UPDATE implementation_plan SET current_version_id=NULL WHERE id=:id"),
                    {"id": plan_id},
                )
            if prd_id:
                connection.execute(
                    text("UPDATE prd SET current_version_id=NULL WHERE id=:id"), {"id": prd_id}
                )
            if requirement_id:
                connection.execute(
                    text("UPDATE requirement SET current_version_id=NULL WHERE id=:id"),
                    {"id": requirement_id},
                )
            if plan_id:
                connection.execute(
                    text(
                        "UPDATE confirmation_round SET source_round_id=NULL "
                        "WHERE implementation_plan_id=:id"
                    ),
                    {"id": plan_id},
                )
                connection.execute(
                    text(
                        "UPDATE implementation_plan_version SET source_version_id=NULL "
                        "WHERE implementation_plan_id=:id"
                    ),
                    {"id": plan_id},
                )
            for table, column, value in (
                ("confirmation_round", "implementation_plan_id", plan_id),
                ("implementation_plan_version", "implementation_plan_id", plan_id),
                ("implementation_plan", "id", plan_id),
                ("design_review_scope", "design_review_id", review_id),
                ("design_review", "id", review_id),
                ("prd_version", "prd_id", prd_id),
                ("prd", "id", prd_id),
                ("idempotency_record", "user_id", user_id),
                ("idempotency_record", "user_id", reader_id),
            ):
                if value:
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE {column}=:value"), {"value": value}
                    )
            if requirement_version_id:
                connection.execute(
                    text("DELETE FROM requirement_version WHERE id=:id"),
                    {"id": requirement_version_id},
                )
            if requirement_id:
                connection.execute(
                    text("DELETE FROM requirement WHERE id=:id"), {"id": requirement_id}
                )
            if project_version_id:
                connection.execute(
                    text("DELETE FROM project_version WHERE id=:id"), {"id": project_version_id}
                )
            if project_id:
                connection.execute(
                    text("DELETE FROM project_member WHERE project_id=:id"), {"id": project_id}
                )
                connection.execute(text("DELETE FROM project WHERE id=:id"), {"id": project_id})
            for value in (user_id, reader_id):
                if value:
                    connection.execute(text("DELETE FROM user_account WHERE id=:id"), {"id": value})
        engine.dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
