from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import unittest
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.modules.requirements.service import RequirementService
from app.platform.config import get_settings
from app.platform.database import get_engine
from app.platform.errors import ApiError


pytestmark = pytest.mark.integration


class RequirementMySqlIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_url = os.getenv("MYSQL_TEST_DATABASE_URL")
        if not test_url:
            raise AssertionError("MYSQL_TEST_DATABASE_URL must be configured for this real Gate")

        parsed_url = make_url(test_url)
        database_name = parsed_url.database or ""
        if not database_name.endswith("_test"):
            raise AssertionError("Requirement integration Gate requires a dedicated *_test database")

        cls._old_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = test_url
        get_engine.cache_clear()
        get_settings.cache_clear()
        cls.engine = get_engine()

        with cls.engine.connect() as connection:
            cls.server_version = str(connection.execute(text("SELECT VERSION()")).scalar_one())
            if re.match(r"^8\.4(?:\.|$)", cls.server_version) is None:
                raise AssertionError("Requirement integration Gate requires MySQL 8.4.x")
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if head != "20260729_0004":
                raise AssertionError("Requirement integration Gate requires Alembic head 20260729_0004")

        cls.database_name = database_name
        cls.endpoint = f"{parsed_url.host}:{parsed_url.port or 3306}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
        if cls._old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._old_database_url

    def setUp(self) -> None:
        self.token = f"req_mysql_{uuid.uuid4().hex}"
        self.trace_prefix = f"trace_{self.token}"
        self.failure_constraint_name: str | None = None
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.engine.begin() as connection:
            self.user_id = int(
                connection.execute(
                    text(
                        "INSERT INTO user_account "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                        "email,password_hash,display_name,system_role,status,last_login_at) VALUES "
                        "(:now,NULL,:now,NULL,1,NULL,NULL,:email,'integration-placeholder',"
                        ":display_name,'user','active',NULL)"
                    ),
                    {
                        "now": now,
                        "email": f"{self.token}@example.test",
                        "display_name": self.token,
                    },
                ).lastrowid
            )
            self.project_id = int(
                connection.execute(
                    text(
                        "INSERT INTO project "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                        "owner_user_id,name,description,status,last_module) VALUES "
                        "(:now,:user_id,:now,:user_id,1,NULL,NULL,:user_id,:name,NULL,'active','requirement')"
                    ),
                    {"now": now, "user_id": self.user_id, "name": self.token},
                ).lastrowid
            )
            connection.execute(
                text(
                    "INSERT INTO project_member "
                    "(created_at,created_by,updated_at,updated_by,row_version,project_id,user_id,role_code,status) "
                    "VALUES (:now,:user_id,:now,:user_id,1,:project_id,:user_id,'owner','active')"
                ),
                {"now": now, "user_id": self.user_id, "project_id": self.project_id},
            )
            self.project_version_id = int(
                connection.execute(
                    text(
                        "INSERT INTO project_version "
                        "(created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                        "project_id,parent_version_id,version_no,version_name,creation_reason,lifecycle_status,"
                        "workflow_node,is_working) VALUES "
                        "(:now,:user_id,:now,:user_id,1,NULL,NULL,:project_id,NULL,'1','Integration',"
                        "'requirement-integration','draft','requirement',1)"
                    ),
                    {"now": now, "user_id": self.user_id, "project_id": self.project_id},
                ).lastrowid
            )
        self.service = RequirementService()

    def tearDown(self) -> None:
        if self.failure_constraint_name is not None:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE business_event_outbox "
                        f"DROP CHECK `{self.failure_constraint_name}`"
                    )
                )
            self.failure_constraint_name = None

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM business_event_outbox "
                    "WHERE JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id')) LIKE :trace_prefix"
                ),
                {"trace_prefix": f"{self.trace_prefix}%"},
            )
            connection.execute(
                text("DELETE FROM operation_audit_log WHERE trace_id LIKE :trace_prefix"),
                {"trace_prefix": f"{self.trace_prefix}%"},
            )
            connection.execute(
                text("DELETE FROM requirement_version WHERE created_by=:user_id"),
                {"user_id": self.user_id},
            )
            connection.execute(
                text("DELETE FROM idempotency_record WHERE user_id=:user_id"),
                {"user_id": self.user_id},
            )
            connection.execute(
                text("DELETE FROM requirement WHERE project_version_id=:project_version_id"),
                {"project_version_id": self.project_version_id},
            )
            connection.execute(
                text("DELETE FROM project_version WHERE id=:project_version_id"),
                {"project_version_id": self.project_version_id},
            )
            connection.execute(
                text("DELETE FROM project_member WHERE project_id=:project_id"),
                {"project_id": self.project_id},
            )
            connection.execute(
                text("DELETE FROM project WHERE id=:project_id"),
                {"project_id": self.project_id},
            )
            connection.execute(
                text("DELETE FROM user_account WHERE id=:user_id"),
                {"user_id": self.user_id},
            )

    def _counts(self) -> tuple[int, int, int, int, int]:
        with self.engine.connect() as connection:
            parameters = {
                "project_version_id": self.project_version_id,
                "trace_prefix": f"{self.trace_prefix}%",
                "user_id": self.user_id,
            }
            return (
                int(
                    connection.execute(
                        text("SELECT COUNT(*) FROM requirement WHERE project_version_id=:project_version_id"),
                        parameters,
                    ).scalar_one()
                ),
                int(
                    connection.execute(
                        text("SELECT COUNT(*) FROM requirement_version WHERE created_by=:user_id"),
                        parameters,
                    ).scalar_one()
                ),
                int(
                    connection.execute(
                        text("SELECT COUNT(*) FROM operation_audit_log WHERE trace_id LIKE :trace_prefix"),
                        parameters,
                    ).scalar_one()
                ),
                int(
                    connection.execute(
                        text(
                            "SELECT COUNT(*) FROM business_event_outbox "
                            "WHERE aggregate_type='requirement' AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id')) "
                            "LIKE :trace_prefix"
                        ),
                        parameters,
                    ).scalar_one()
                ),
                int(
                    connection.execute(
                        text("SELECT COUNT(*) FROM idempotency_record WHERE user_id=:user_id"),
                        parameters,
                    ).scalar_one()
                ),
            )

    def test_create_idempotency_and_revision_persist_real_facts(self) -> None:
        raw_input = "  真实 MySQL\u00a0Requirement\n第二行  "
        payload = {"title": self.token, "raw_input": raw_input, "source_refs": []}
        key = f"create-{self.token}"
        create_trace = f"{self.trace_prefix}_create"

        created = self.service.create_requirement(
            version_id=self.project_version_id,
            user_id=self.user_id,
            payload=payload,
            key=key,
            trace_id=create_trace,
        )
        requirement_id = int(created["requirement"]["id"])
        version_1_id = int(created["current_version"]["id"])

        with self.engine.connect() as connection:
            requirement = connection.execute(
                text("SELECT * FROM requirement WHERE id=:requirement_id"),
                {"requirement_id": requirement_id},
            ).mappings().one()
            version_1 = connection.execute(
                text("SELECT * FROM requirement_version WHERE id=:version_id"),
                {"version_id": version_1_id},
            ).mappings().one()
            audit = connection.execute(
                text("SELECT * FROM operation_audit_log WHERE trace_id=:trace_id"),
                {"trace_id": create_trace},
            ).mappings().one()
            outbox = connection.execute(
                text(
                    "SELECT * FROM business_event_outbox "
                    "WHERE aggregate_type='requirement' AND aggregate_id=:requirement_id"
                ),
                {"requirement_id": requirement_id},
            ).mappings().one()
            idempotency = connection.execute(
                text(
                    "SELECT * FROM idempotency_record "
                    "WHERE user_id=:user_id AND idempotency_key=:key"
                ),
                {"user_id": self.user_id, "key": key},
            ).mappings().one()

        content_1 = version_1["content_json"]
        if isinstance(content_1, str):
            content_1 = json.loads(content_1)
        self.assertEqual(requirement["current_version_id"], version_1_id)
        self.assertEqual(content_1["raw_input"], raw_input)
        self.assertEqual(
            content_1["raw_input_ref"]["content_hash"],
            hashlib.sha256(raw_input.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            version_1["content_hash"],
            hashlib.sha256(
                json.dumps(
                    content_1,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual((audit["object_id"], audit["object_version_id"]), (requirement_id, version_1_id))
        self.assertEqual((outbox["aggregate_id"], outbox["aggregate_version"]), (requirement_id, 1))
        self.assertEqual((idempotency["status"], int(idempotency["response_ref"])), ("completed", requirement_id))
        self.assertEqual(self._counts(), (1, 1, 1, 1, 1))

        replayed = self.service.create_requirement(
            version_id=self.project_version_id,
            user_id=self.user_id,
            payload=payload,
            key=key,
            trace_id=f"{self.trace_prefix}_replay",
        )
        self.assertEqual(replayed["requirement"]["id"], created["requirement"]["id"])
        self.assertEqual(replayed["current_version"]["id"], created["current_version"]["id"])
        self.assertEqual(self._counts(), (1, 1, 1, 1, 1))

        with self.assertRaises(ApiError) as conflict:
            self.service.create_requirement(
                version_id=self.project_version_id,
                user_id=self.user_id,
                payload={**payload, "raw_input": f"{raw_input} changed"},
                key=key,
                trace_id=f"{self.trace_prefix}_conflict",
            )
        self.assertEqual((conflict.exception.code, conflict.exception.http_status), ("IDEMPOTENCY_CONFLICT", 409))
        self.assertEqual(self._counts(), (1, 1, 1, 1, 1))

        version_1_before = copy.deepcopy(dict(version_1))
        revision_trace = f"{self.trace_prefix}_revision"
        revised = self.service.revise(
            version_id=version_1_id,
            user_id=self.user_id,
            payload={"expected_version": 1, "title": f"{self.token}-revised"},
            trace_id=revision_trace,
        )
        version_2_id = int(revised["id"])

        with self.engine.connect() as connection:
            requirement_after = connection.execute(
                text("SELECT * FROM requirement WHERE id=:requirement_id"),
                {"requirement_id": requirement_id},
            ).mappings().one()
            versions = connection.execute(
                text(
                    "SELECT * FROM requirement_version WHERE requirement_id=:requirement_id "
                    "ORDER BY CAST(version_no AS UNSIGNED)"
                ),
                {"requirement_id": requirement_id},
            ).mappings().all()
            audits = connection.execute(
                text(
                    "SELECT operation_name,object_version_id FROM operation_audit_log "
                    "WHERE trace_id LIKE :trace_prefix ORDER BY id"
                ),
                {"trace_prefix": f"{self.trace_prefix}%"},
            ).all()
            outboxes = connection.execute(
                text(
                    "SELECT aggregate_version FROM business_event_outbox "
                    "WHERE aggregate_type='requirement' AND aggregate_id=:requirement_id "
                    "ORDER BY aggregate_version"
                ),
                {"requirement_id": requirement_id},
            ).scalars().all()

        self.assertEqual(len(versions), 2)
        version_1_after, version_2 = versions
        self.assertEqual(version_1_after["id"], version_1_id)
        self.assertEqual(version_1_after["content_json"], version_1_before["content_json"])
        self.assertEqual(version_1_after["content_hash"], version_1_before["content_hash"])
        self.assertEqual(version_2["id"], version_2_id)
        self.assertEqual(version_2["source_version_id"], version_1_id)
        self.assertEqual(version_2["version_no"], "2")
        content_2 = version_2["content_json"]
        if isinstance(content_2, str):
            content_2 = json.loads(content_2)
        self.assertEqual(content_2["raw_input"], raw_input)
        self.assertEqual(requirement_after["current_version_id"], version_2_id)
        self.assertEqual(requirement_after["row_version"], 2)
        self.assertEqual(
            audits,
            [("requirement.create", version_1_id), ("requirement.version.revised", version_2_id)],
        )
        self.assertEqual(outboxes, [1, 2])
        self.assertEqual(self._counts(), (1, 2, 2, 2, 1))

    def test_create_rolls_back_all_real_facts_when_outbox_insert_fails(self) -> None:
        constraint_name = f"chk_{uuid.uuid4().hex}"
        trace_id = f"{self.trace_prefix}_rollback"
        constraint_sql = (
            "ALTER TABLE business_event_outbox "
            f"ADD CONSTRAINT `{constraint_name}` CHECK "
            f"(JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.trace_id')) <> '{trace_id}')"
        )
        with self.engine.begin() as connection:
            connection.execute(text(constraint_sql))
        self.failure_constraint_name = constraint_name

        with self.assertRaises(DBAPIError):
            self.service.create_requirement(
                version_id=self.project_version_id,
                user_id=self.user_id,
                payload={"title": f"{self.token}-rollback", "raw_input": "rollback", "source_refs": []},
                key=f"rollback-{self.token}",
                trace_id=trace_id,
            )

        self.assertEqual(self._counts(), (0, 0, 0, 0, 0))
