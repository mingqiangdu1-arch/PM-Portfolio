from __future__ import annotations

import json
import os
import re
import unittest
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.modules.prds.service import PrdService
from app.platform.config import get_settings
from app.platform.database import get_engine
from app.platform.errors import ApiError


pytestmark = pytest.mark.integration


def _content(label: str) -> dict:
    return {
        "schema_version": "prd.mvp2.v1",
        "background": f"Background {label}",
        "goal": f"Goal {label}",
        "primary_user": "Owner",
        "in_scope": [f"Scope {label}"],
        "out_of_scope": [f"Out {label}"],
        "core_workflow": [f"Workflow {label}"],
        "key_rules": [f"Rule {label}"],
        "exceptions_and_boundaries": [],
        "acceptance_criteria": [f"Accept {label}"],
    }


class PrdMySqlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_url = os.getenv("MYSQL_TEST_DATABASE_URL")
        if not test_url:
            raise AssertionError("MYSQL_TEST_DATABASE_URL must be configured for this real Gate")
        if not (make_url(test_url).database or "").endswith("_test"):
            raise AssertionError("PRD integration Gate requires a dedicated *_test database")
        cls.old_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = test_url
        get_engine.cache_clear()
        get_settings.cache_clear()
        cls.engine = get_engine()
        with cls.engine.connect() as connection:
            cls.server_version = str(connection.execute(text("SELECT VERSION()")).scalar_one())
            cls.head = str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
        if re.match(r"^8\.4(?:\.|$)", cls.server_version) is None or cls.head != "20260821_0005":
            raise AssertionError("PRD integration Gate requires MySQL 8.4 and Alembic 20260821_0005")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
        if cls.old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.old_url

    def setUp(self) -> None:
        self.token = f"prd_{uuid.uuid4().hex}"
        self.trace = f"trace_{self.token}"
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.engine.begin() as connection:
            self.user_id = int(connection.execute(text("INSERT INTO user_account (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,email,password_hash,display_name,system_role,status,last_login_at) VALUES (:now,NULL,:now,NULL,1,NULL,NULL,:email,'placeholder',:name,'user','active',NULL)"), {"now": now, "email": f"{self.token}@example.test", "name": self.token}).lastrowid)
            self.reader_id = int(connection.execute(text("INSERT INTO user_account (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,email,password_hash,display_name,system_role,status,last_login_at) VALUES (:now,NULL,:now,NULL,1,NULL,NULL,:email,'placeholder',:name,'user','active',NULL)"), {"now": now, "email": f"reader-{self.token}@example.test", "name": f"reader-{self.token}"}).lastrowid)
            self.project_id = int(connection.execute(text("INSERT INTO project (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,owner_user_id,name,description,status,last_module) VALUES (:now,:user,:now,:user,1,NULL,NULL,:user,:name,NULL,'active','product_design')"), {"now": now, "user": self.user_id, "name": self.token}).lastrowid)
            connection.execute(text("INSERT INTO project_member (created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) VALUES (:now,:user,:now,:user,1,:project,:user,'owner','active')"), {"now": now, "user": self.user_id, "project": self.project_id})
            connection.execute(text("INSERT INTO project_member (created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) VALUES (:now,:owner,:now,:owner,1,:project,:user,'implementer','active')"), {"now": now, "owner": self.user_id, "project": self.project_id, "user": self.reader_id})
            self.project_version_id = int(connection.execute(text("INSERT INTO project_version (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,workflow_node,is_working) VALUES (:now,:user,:now,:user,1,NULL,NULL,:project,NULL,'1','PRD Integration','integration','draft','product_design',1)"), {"now": now, "user": self.user_id, "project": self.project_id}).lastrowid)
            self.requirement_id = int(connection.execute(text("INSERT INTO requirement (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,title,source_type,priority,status,current_version_id) VALUES (:now,:user,:now,:user,1,NULL,NULL,:version,:title,'manual','normal','effective',NULL)"), {"now": now, "user": self.user_id, "version": self.project_version_id, "title": self.token}).lastrowid)
            self.requirement_version_id = int(connection.execute(text("INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) VALUES (:now,:user,:requirement,NULL,'1','json','{}',:hash,'confirmed',0,NULL,NULL,1)"), {"now": now, "user": self.user_id, "requirement": self.requirement_id, "hash": "a" * 64}).lastrowid)
            connection.execute(text("UPDATE requirement SET current_version_id=:version_id WHERE id=:id"), {"version_id": self.requirement_version_id, "id": self.requirement_id})
        self.service = PrdService()

    def tearDown(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM business_event_outbox WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id'))=:trace"), {"trace": self.trace})
            connection.execute(text("DELETE FROM operation_audit_log WHERE trace_id=:trace"), {"trace": self.trace})
            connection.execute(text("DELETE FROM design_review_scope WHERE created_by=:user"), {"user": self.user_id})
            connection.execute(text("DELETE FROM design_review WHERE created_by=:user"), {"user": self.user_id})
            connection.execute(text("DELETE FROM prd_version WHERE created_by=:user"), {"user": self.user_id})
            connection.execute(text("DELETE FROM prd WHERE created_by=:user"), {"user": self.user_id})
            connection.execute(text("DELETE FROM idempotency_record WHERE user_id=:user"), {"user": self.user_id})
            connection.execute(text("DELETE FROM requirement_version WHERE id=:id"), {"id": self.requirement_version_id})
            connection.execute(text("DELETE FROM requirement WHERE id=:id"), {"id": self.requirement_id})
            connection.execute(text("DELETE FROM project_version WHERE id=:id"), {"id": self.project_version_id})
            connection.execute(text("DELETE FROM project_member WHERE project_id=:project"), {"project": self.project_id})
            connection.execute(text("DELETE FROM project WHERE id=:id"), {"id": self.project_id})
            connection.execute(text("DELETE FROM user_account WHERE id=:id"), {"id": self.user_id})
            connection.execute(text("DELETE FROM user_account WHERE id=:id"), {"id": self.reader_id})

    def test_prd_review_closed_loop_is_immutable_idempotent_and_confirmed(self) -> None:
        created = self.service.create_prd(version_id=self.project_version_id, user_id=self.user_id, payload={"source_requirement_version_id": str(self.requirement_version_id), "name": "Main PRD"}, key=f"create-{self.token}", trace_id=self.trace)
        prd_id = int(created["prd"]["id"])
        replay = self.service.create_prd(version_id=self.project_version_id, user_id=self.user_id, payload={"source_requirement_version_id": str(self.requirement_version_id), "name": "Main PRD"}, key=f"create-{self.token}", trace_id=self.trace)
        self.assertEqual(replay["prd"]["id"], str(prd_id))
        with self.assertRaises(ApiError) as idempotency_conflict:
            self.service.create_prd(version_id=self.project_version_id, user_id=self.user_id, payload={"source_requirement_version_id": str(self.requirement_version_id), "name": "Different"}, key=f"create-{self.token}", trace_id=self.trace)
        self.assertEqual(idempotency_conflict.exception.code, "IDEMPOTENCY_CONFLICT")

        saved_1 = self.service.save_version(prd_id=prd_id, user_id=self.user_id, payload={"expected_version": 1, "content_json": _content("one"), "change_note": "first save"}, key=f"save-1-{self.token}", trace_id=self.trace)
        version_1 = int(saved_1["prd_version"]["id"])
        self.assertIsNone(saved_1["prd_version"]["source_version_id"])
        with self.assertRaises(ApiError) as conflict:
            self.service.save_version(prd_id=prd_id, user_id=self.user_id, payload={"expected_version": 1, "content_json": _content("stale"), "change_note": "stale"}, key=f"stale-{self.token}", trace_id=self.trace)
        self.assertEqual(conflict.exception.code, "VERSION_CONFLICT")

        review_1 = self.service.submit_review(version_id=self.project_version_id, user_id=self.user_id, payload={"prd_id": str(prd_id), "prd_version_id": str(version_1), "content_hash": saved_1["prd_version"]["content_hash"], "expected_version": 2}, key=f"submit-1-{self.token}", trace_id=self.trace)
        review_1_id = int(review_1["design_review"]["id"])
        requested = self.service.decide_review(review_id=review_1_id, user_id=self.user_id, payload={"expected_version": 1, "decision": "changes_requested", "summary": "Need a clearer boundary"}, key=f"request-{self.token}", trace_id=self.trace)
        self.assertEqual(requested["design_review"]["status"], "changes_requested")

        saved_2 = self.service.save_version(prd_id=prd_id, user_id=self.user_id, payload={"expected_version": 4, "content_json": _content("two"), "change_note": "revision"}, key=f"save-2-{self.token}", trace_id=self.trace)
        version_2 = int(saved_2["prd_version"]["id"])
        self.assertEqual(saved_2["prd_version"]["source_version_id"], str(version_1))
        review_2 = self.service.submit_review(version_id=self.project_version_id, user_id=self.user_id, payload={"prd_id": str(prd_id), "prd_version_id": str(version_2), "content_hash": saved_2["prd_version"]["content_hash"], "expected_version": 5}, key=f"submit-2-{self.token}", trace_id=self.trace)
        review_2_id = int(review_2["design_review"]["id"])
        passed = self.service.decide_review(review_id=review_2_id, user_id=self.user_id, payload={"expected_version": 1, "decision": "pass"}, key=f"pass-{self.token}", trace_id=self.trace)
        self.assertEqual(passed["design_review"]["status"], "passed")

        with self.engine.connect() as connection:
            prd = connection.execute(text("SELECT status,current_version_id,row_version FROM prd WHERE id=:id"), {"id": prd_id}).one()
            versions = connection.execute(text("SELECT id,content_hash,is_effective FROM prd_version WHERE prd_id=:id ORDER BY id"), {"id": prd_id}).all()
            audit_count = connection.execute(text("SELECT COUNT(*) FROM operation_audit_log WHERE trace_id=:trace"), {"trace": self.trace}).scalar_one()
            outbox_count = connection.execute(text("SELECT COUNT(*) FROM business_event_outbox WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id'))=:trace"), {"trace": self.trace}).scalar_one()
        self.assertEqual(tuple(prd), ("confirmed", version_2, 7))
        self.assertEqual([(row.id, row.is_effective) for row in versions], [(version_1, 0), (version_2, 1)])
        self.assertEqual(versions[0].content_hash, saved_1["prd_version"]["content_hash"])
        self.assertEqual((audit_count, outbox_count), (7, 7))
        with self.assertRaises(ApiError) as immutable:
            self.service.save_version(prd_id=prd_id, user_id=self.user_id, payload={"expected_version": 7, "content_json": _content("three"), "change_note": "forbidden"}, key=f"save-3-{self.token}", trace_id=self.trace)
        self.assertEqual(immutable.exception.code, "INVALID_STATE")

    def test_active_member_read_owner_write_and_source_version_guards(self) -> None:
        readable = self.service.list_prds(version_id=self.project_version_id, user_id=self.reader_id)
        self.assertEqual(readable, {"items": [], "has_more": False})
        with self.assertRaises(ApiError) as owner_only:
            self.service.create_prd(version_id=self.project_version_id, user_id=self.reader_id, payload={"source_requirement_version_id": str(self.requirement_version_id), "name": "Reader PRD"}, key=f"reader-{self.token}", trace_id=self.trace)
        self.assertEqual(owner_only.exception.code, "FORBIDDEN")

        with self.engine.begin() as connection:
            other_version_id = int(connection.execute(text("INSERT INTO project_version (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,workflow_node,is_working) VALUES (:now,:user,:now,:user,1,NULL,NULL,:project,NULL,'2','Other version','integration','draft','product_design',0)"), {"now": datetime.now(UTC).replace(tzinfo=None), "user": self.user_id, "project": self.project_id}).lastrowid)
            other_requirement_id = int(connection.execute(text("INSERT INTO requirement (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,project_version_id,title,source_type,priority,status,current_version_id) VALUES (:now,:user,:now,:user,1,NULL,NULL,:version,:title,'manual','normal','effective',NULL)"), {"now": datetime.now(UTC).replace(tzinfo=None), "user": self.user_id, "version": other_version_id, "title": f"other-{self.token}"}).lastrowid)
            other_requirement_version_id = int(connection.execute(text("INSERT INTO requirement_version (created_at,created_by,requirement_id,source_version_id,version_no,content_format,content_json,content_hash,confirmation_status,unresolved_count,risk_acceptance_json,created_from_ai_result_id,is_effective) VALUES (:now,:user,:requirement,NULL,'1','json','{}',:hash,'confirmed',0,NULL,NULL,1)"), {"now": datetime.now(UTC).replace(tzinfo=None), "user": self.user_id, "requirement": other_requirement_id, "hash": "b" * 64}).lastrowid)
        try:
            with self.assertRaises(ApiError) as wrong_source:
                self.service.create_prd(version_id=self.project_version_id, user_id=self.user_id, payload={"source_requirement_version_id": str(other_requirement_version_id), "name": "Wrong source"}, key=f"wrong-source-{self.token}", trace_id=self.trace)
            self.assertEqual(wrong_source.exception.code, "NOT_FOUND")
        finally:
            with self.engine.begin() as connection:
                connection.execute(text("DELETE FROM requirement_version WHERE id=:id"), {"id": other_requirement_version_id})
                connection.execute(text("DELETE FROM requirement WHERE id=:id"), {"id": other_requirement_id})
                connection.execute(text("DELETE FROM project_version WHERE id=:id"), {"id": other_version_id})
