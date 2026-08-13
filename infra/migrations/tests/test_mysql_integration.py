from __future__ import annotations

import os
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


MYSQL_TEST_URL = os.getenv("MYSQL_TEST_DATABASE_URL")


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
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            server_version = connection.execute(text("SELECT VERSION()")).scalar_one()
            self.assertRegex(server_version, r"^8\.4(?:\.|$)")
            self.assertEqual(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one(),
                "20260729_0004",
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
