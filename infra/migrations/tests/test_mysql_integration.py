from __future__ import annotations

import os
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


MYSQL_TEST_URL = os.getenv("MYSQL_TEST_DATABASE_URL")


def _schema_signature(connection) -> set[tuple]:
    from sqlalchemy import text

    signature = {
        ("COLUMN", *row)
        for row in connection.execute(
            text(
                "SELECT table_name,column_name,column_type,is_nullable "
                "FROM information_schema.columns WHERE table_schema=DATABASE()"
            )
        )
    }
    signature.update(
        ("INDEX", *row)
        for row in connection.execute(
            text(
                "SELECT table_name,index_name,seq_in_index,column_name,non_unique "
                "FROM information_schema.statistics WHERE table_schema=DATABASE()"
            )
        )
    )
    signature.update(
        ("FOREIGN_KEY", *row)
        for row in connection.execute(
            text(
                "SELECT k.table_name,k.constraint_name,k.column_name,"
                "k.referenced_table_name,k.referenced_column_name,r.update_rule,r.delete_rule "
                "FROM information_schema.key_column_usage k "
                "JOIN information_schema.referential_constraints r "
                "ON r.constraint_schema=k.constraint_schema AND r.constraint_name=k.constraint_name "
                "WHERE k.table_schema=DATABASE() AND k.referenced_table_name IS NOT NULL"
            )
        )
    )
    return signature


@unittest.skipUnless(MYSQL_TEST_URL, "MYSQL_TEST_DATABASE_URL is not configured")
class MySqlMigrationIntegrationTests(unittest.TestCase):
    def test_empty_existing_repeated_upgrade_and_protected_downgrade(self) -> None:
        assert MYSQL_TEST_URL
        database_name = urlsplit(MYSQL_TEST_URL).path.rsplit("/", 1)[-1]
        self.assertTrue(
            database_name.endswith("_test"),
            "integration migration tests require a dedicated *_test database",
        )
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text

        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root))
        config.set_main_option("sqlalchemy.url", MYSQL_TEST_URL)
        engine = create_engine(MYSQL_TEST_URL)

        command.downgrade(config, "base")
        command.upgrade(config, "20260729_0004")
        with engine.connect() as connection:
            schema_at_0004 = _schema_signature(connection)
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            schema_at_head = _schema_signature(connection)
            self.assertFalse(schema_at_0004 - schema_at_head)
            self.assertEqual(
                schema_at_head - schema_at_0004,
                {
                    ("COLUMN", "prd", "source_requirement_version_id", "bigint unsigned", "NO"),
                    (
                        "INDEX",
                        "prd",
                        "idx_prd_source_requirement_version",
                        1,
                        "source_requirement_version_id",
                        1,
                    ),
                    (
                        "FOREIGN_KEY",
                        "prd",
                        "fk_prd_source_requirement_version_id",
                        "source_requirement_version_id",
                        "requirement_version",
                        "id",
                        "RESTRICT",
                        "RESTRICT",
                    ),
                    ("COLUMN", "implementation_plan", "source_prd_version_id", "bigint unsigned", "NO"),
                    ("COLUMN", "implementation_plan", "source_design_review_id", "bigint unsigned", "NO"),
                    ("COLUMN", "confirmation_round", "source_round_id", "bigint unsigned", "YES"),
                    ("COLUMN", "confirmation_round", "implementation_summary", "text", "NO"),
                    ("COLUMN", "confirmation_round", "readiness_json", "json", "NO"),
                    ("COLUMN", "confirmation_round", "draft_plan_key", "bigint unsigned", "YES"),
                    ("INDEX", "implementation_plan", "idx_implementation_plan_source_prd_version", 1, "source_prd_version_id", 1),
                    ("INDEX", "implementation_plan", "idx_implementation_plan_source_design_review", 1, "source_design_review_id", 1),
                    ("INDEX", "implementation_plan_version", "fk_implementation_plan_version_source_version_id", 1, "source_version_id", 1),
                    ("INDEX", "implementation_plan", "fk_implementation_plan_current_version_id", 1, "current_version_id", 1),
                    ("INDEX", "confirmation_round", "idx_confirmation_round_source_round", 1, "source_round_id", 1),
                    ("INDEX", "confirmation_round", "uk_plan_one_draft_round", 1, "draft_plan_key", 0),
                    ("FOREIGN_KEY", "implementation_plan", "fk_implementation_plan_source_prd_version_id", "source_prd_version_id", "prd_version", "id", "RESTRICT", "RESTRICT"),
                    ("FOREIGN_KEY", "implementation_plan", "fk_implementation_plan_source_design_review_id", "source_design_review_id", "design_review", "id", "RESTRICT", "RESTRICT"),
                    ("FOREIGN_KEY", "implementation_plan", "fk_implementation_plan_current_version_id", "current_version_id", "implementation_plan_version", "id", "RESTRICT", "RESTRICT"),
                    ("FOREIGN_KEY", "implementation_plan_version", "fk_implementation_plan_version_source_version_id", "source_version_id", "implementation_plan_version", "id", "RESTRICT", "RESTRICT"),
                    ("FOREIGN_KEY", "confirmation_round", "fk_confirmation_round_source_round_id", "source_round_id", "confirmation_round", "id", "RESTRICT", "RESTRICT"),
                },
            )
            server_version = connection.execute(text("SELECT VERSION()")).scalar_one()
            self.assertRegex(server_version, r"^8\.4(?:\.|$)")
            self.assertEqual(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one(),
                "20260823_0006",
            )
            storage_columns = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema=DATABASE() AND table_name='file_version' "
                    "AND column_name='storage_version_id'"
                )
            ).scalar_one()
            storage_indexes = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema=DATABASE() AND table_name='file_version' "
                    "AND index_name='idx_file_storage_version'"
                )
            ).scalar_one()
            self.assertEqual((storage_columns, storage_indexes), (1, 1))
            prd_column = connection.execute(
                text(
                    "SELECT column_type,is_nullable FROM information_schema.columns "
                    "WHERE table_schema=DATABASE() AND table_name='prd' "
                    "AND column_name='source_requirement_version_id'"
                )
            ).one()
            prd_index = connection.execute(
                text(
                    "SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index),MIN(non_unique) "
                    "FROM information_schema.statistics "
                    "WHERE table_schema=DATABASE() AND table_name='prd' "
                    "AND index_name='idx_prd_source_requirement_version'"
                )
            ).one()
            prd_fk = connection.execute(
                text(
                    "SELECT k.referenced_table_name,k.referenced_column_name,r.update_rule,r.delete_rule "
                    "FROM information_schema.key_column_usage k "
                    "JOIN information_schema.referential_constraints r "
                    "ON r.constraint_schema=k.constraint_schema AND r.constraint_name=k.constraint_name "
                    "WHERE k.table_schema=DATABASE() AND k.table_name='prd' "
                    "AND k.constraint_name='fk_prd_source_requirement_version_id' "
                    "AND k.column_name='source_requirement_version_id'"
                )
            ).one()
            self.assertEqual(tuple(prd_column), ("bigint unsigned", "NO"))
            self.assertEqual(tuple(prd_index), ("source_requirement_version_id", 1))
            self.assertEqual(
                tuple(prd_fk), ("requirement_version", "id", "RESTRICT", "RESTRICT")
            )
            family_index_columns = connection.execute(
                text(
                    "SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) "
                    "FROM information_schema.statistics "
                    "WHERE table_schema=DATABASE() AND table_name='user_session' "
                    "AND index_name='idx_session_family_state'"
                )
            ).scalar_one()
            unique_successor = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.statistics "
                    "WHERE table_schema=DATABASE() AND table_name='user_session' "
                    "AND index_name='uk_user_session_replaced_by' AND non_unique=0"
                )
            ).scalar_one()
            successor_fk = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.key_column_usage "
                    "WHERE table_schema=DATABASE() AND table_name='user_session' "
                    "AND constraint_name='fk_user_session_replaced_by_session_id' "
                    "AND column_name='replaced_by_session_id' "
                    "AND referenced_table_name='user_session' AND referenced_column_name='id'"
                )
            ).scalar_one()
            self.assertEqual(
                family_index_columns,
                "token_family_id,revoked_at,expires_at,id",
            )
            self.assertEqual((unique_successor, successor_fk), (1, 1))

            generated = connection.execute(
                text(
                    "SELECT extra,generation_expression FROM information_schema.columns "
                    "WHERE table_schema=DATABASE() AND table_name='confirmation_round' "
                    "AND column_name='draft_plan_key'"
                )
            ).one()
            self.assertEqual(generated[0], "STORED GENERATED")
            self.assertEqual(
                generated[1].replace("\\'", "'"),
                "(case when (`status` = _utf8mb4'draft') then `implementation_plan_id` end)",
            )

    def test_guard_fail_is_before_ddl_and_preserves_schema_and_data(self) -> None:
        assert MYSQL_TEST_URL
        database_name = urlsplit(MYSQL_TEST_URL).path.rsplit("/", 1)[-1]
        self.assertTrue(database_name.endswith("_test"))
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text

        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root))
        config.set_main_option("sqlalchemy.url", MYSQL_TEST_URL)
        engine = create_engine(MYSQL_TEST_URL)
        command.downgrade(config, "base")
        command.upgrade(config, "20260821_0005")
        with engine.begin() as connection:
            identity_before = tuple(
                connection.execute(text("SELECT DATABASE(),CURRENT_USER(),VERSION()")).one()
            )
            self.assertTrue(all(identity_before))
            connection.execute(
                text(
                    "INSERT INTO user_account "
                    "(id,created_at,updated_at,row_version,email,password_hash,display_name,system_role,status) "
                    "VALUES (1,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),1,'mvp3-guard@example.test','fixture',"
                    "'MVP3 Guard','user','active')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO project "
                    "(id,created_at,updated_at,row_version,owner_user_id,name,status) "
                    "VALUES (1,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),1,1,'MVP3 Guard','active')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO project_version "
                    "(id,created_at,updated_at,row_version,project_id,version_no,creation_reason,"
                    "lifecycle_status,workflow_node,is_working) VALUES "
                    "(1,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),1,1,'V1','guard fixture','draft','requirement',0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO implementation_plan "
                    "(created_at,updated_at,row_version,project_version_id,name,status) "
                    "VALUES (UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),1,1,'guard-fixture','draft')"
                )
            )
            before_signature = _schema_signature(connection)
            before_count = connection.execute(
                text("SELECT COUNT(*) FROM implementation_plan")
            ).scalar_one()
        with self.assertRaisesRegex(RuntimeError, "expected 0/0/0"):
            command.upgrade(config, "head")
        with engine.connect() as connection:
            self.assertEqual(_schema_signature(connection), before_signature)
            self.assertEqual(
                connection.execute(text("SELECT COUNT(*) FROM implementation_plan")).scalar_one(),
                before_count,
            )
            self.assertEqual(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one(),
                "20260821_0005",
            )
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM implementation_plan"))
        command.downgrade(config, "base")
        engine.dispose()

        command.downgrade(config, "base")
        command.upgrade(config, "20260729_0001")
        now = datetime.utcnow()
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO user_account "
                    "(created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                    "email,password_hash,display_name,system_role,status,last_login_at) VALUES "
                    "(:now,NULL,:now,NULL,1,NULL,NULL,'migration@example.test','argon2-placeholder',"
                    "'Migration','user','active',NULL)"
                ),
                {"now": now},
            ).lastrowid
            connection.execute(
                text(
                    "INSERT INTO user_session "
                    "(created_at,created_by,user_id,refresh_token_hash,session_public_id,issued_at,"
                    "expires_at,revoked_at,revoke_reason) VALUES "
                    "(:now,:user_id,:user_id,:hash,:session_id,:now,:now,:now,'migration-fixture')"
                ),
                {"now": now, "user_id": user_id, "hash": "a" * 64, "session_id": "00000000-0000-0000-0000-000000000001"},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT session_public_id,token_family_id FROM user_session")
            ).one()
            self.assertEqual(row.session_public_id, row.token_family_id)
        command.downgrade(config, "20260729_0002")
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text("UPDATE user_session SET revoked_at=NULL"))
        with self.assertRaises(RuntimeError):
            command.downgrade(config, "20260729_0002")
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text("UPDATE user_session SET revoked_at=:now"), {"now": now})
            stored_file_id = connection.execute(
                text(
                    "INSERT INTO stored_file "
                    "(created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,"
                    "owner_user_id,project_id,logical_name,status,current_version_id) VALUES "
                    "(:now,:user_id,:now,:user_id,1,NULL,NULL,:user_id,NULL,'migration-file','active',NULL)"
                ),
                {"now": now, "user_id": user_id},
            ).lastrowid
            connection.execute(
                text(
                    "INSERT INTO file_version "
                    "(created_at,created_by,stored_file_id,version_no,object_key,mime_type,extension,"
                    "size_bytes,checksum_sha256,storage_status,change_note,storage_version_id) VALUES "
                    "(:now,:user_id,:stored_file_id,'V1','migration/final/object','text/plain','txt',"
                    "1,:checksum,'available',NULL,'storage-version-1')"
                ),
                {
                    "now": now,
                    "user_id": user_id,
                    "stored_file_id": stored_file_id,
                    "checksum": "b" * 64,
                },
            )
        with self.assertRaises(RuntimeError):
            command.downgrade(config, "20260729_0003")
        with engine.begin() as connection:
            connection.execute(text("UPDATE file_version SET storage_version_id=NULL"))
        command.downgrade(config, "base")
        engine.dispose()
