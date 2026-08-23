import ast
import importlib.util
import json
import unittest
from pathlib import Path


MIGRATION_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = MIGRATION_ROOT / "schema_catalog.json"
SPRINT1_DELTA_PATH = MIGRATION_ROOT / "sprint1_schema_delta.json"
VERSIONS_ROOT = MIGRATION_ROOT / "versions"
GENERATOR_PATH = MIGRATION_ROOT.parents[0] / "scripts" / "generate_schema_catalog.py"


def catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


class CatalogTests(unittest.TestCase):
    def test_catalog_has_exactly_77_unique_tables(self) -> None:
        names = [table["name"] for table in catalog()["tables"]]
        self.assertEqual(len(names), 77)
        self.assertEqual(len(set(names)), 77)

    def test_all_indexes_reference_declared_columns(self) -> None:
        for table in catalog()["tables"]:
            fields = {field["name"] for field in table["fields"]}
            for index in table["indexes"]:
                self.assertTrue(set(index["columns"]).issubset(fields), (table, index))

    def test_critical_generated_unique_constraints_are_pinned(self) -> None:
        by_name = {table["name"]: table for table in catalog()["tables"]}
        expectations = {
            "project_version": ("current_project_key", "uk_project_one_working"),
            "requirement_version": ("effective_owner_key", "uk_requirement_effective"),
            "prd": ("main_prd_key", "uk_version_one_main_prd"),
            "confirmation_round": ("effective_plan_key", "uk_plan_one_effective_round"),
            "skill_version": ("current_owner_key", "uk_skill_current"),
        }
        for table_name, (column, index_name) in expectations.items():
            fields = {field["name"]: field for field in by_name[table_name]["fields"]}
            indexes = {index["name"]: index for index in by_name[table_name]["indexes"]}
            self.assertTrue(fields[column]["generated"])
            self.assertTrue(indexes[index_name]["unique"])

    def test_file_relation_uses_file_version_not_temporary_url(self) -> None:
        relation = next(table for table in catalog()["tables"] if table["name"] == "file_relation")
        fields = {field["name"] for field in relation["fields"]}
        self.assertIn("file_version_id", fields)
        self.assertNotIn("temporary_url", fields)
        self.assertNotIn("signed_url", fields)

    def test_forbidden_plaintext_secret_columns_do_not_exist(self) -> None:
        forbidden = {"api_key", "access_token", "refresh_token", "password"}
        actual = {
            field["name"]
            for table in catalog()["tables"]
            for field in table["fields"]
        }
        self.assertTrue(forbidden.isdisjoint(actual))

    def test_committed_catalog_matches_the_formal_dictionary(self) -> None:
        spec = importlib.util.spec_from_file_location("schema_generator", GENERATOR_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(catalog(), module.parse())


class RevisionGraphTests(unittest.TestCase):
    def test_alembic_has_one_head(self) -> None:
        revisions: dict[str, str | None] = {}
        for path in VERSIONS_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            values = {
                node.target.id: ast.literal_eval(node.value)
                for node in tree.body
                if isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id in {"revision", "down_revision"}
            }
            revisions[values["revision"]] = values["down_revision"]
        parents = {parent for parent in revisions.values() if parent is not None}
        heads = set(revisions) - parents
        self.assertEqual(heads, {"20260823_0006"})
        self.assertIsNone(revisions["20260729_0001"])
        self.assertEqual(revisions["20260729_0002"], "20260729_0001")
        self.assertEqual(revisions["20260729_0003"], "20260729_0002")
        self.assertEqual(revisions["20260729_0004"], "20260729_0003")
        self.assertEqual(revisions["20260821_0005"], "20260729_0004")
        self.assertEqual(revisions["20260823_0006"], "20260821_0005")

    def test_mvp3_foundation_revision_is_additive_and_fail_closed(self) -> None:
        source = (VERSIONS_ROOT / "20260823_0006_implementation_plan_confirmation_foundation.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('revision: str = "20260823_0006"', source)
        self.assertIn('down_revision: str | None = "20260821_0005"', source)
        self.assertEqual(source.count("op.add_column("), 6)
        self.assertNotIn("op.create_table(", source)
        self.assertNotIn("op.drop_table(", source)
        self.assertNotIn("UPDATE `", source)
        for table in ("implementation_plan", "implementation_plan_version", "confirmation_round"):
            self.assertIn(table, source)
        for expected in (
            "SELECT DATABASE(), CURRENT_USER(), VERSION()",
            "expected 0/0/0",
            "draft_plan_key",
            "uk_plan_one_draft_round",
            "fk_implementation_plan_current_version_id",
            "fk_implementation_plan_version_source_version_id",
        ):
            self.assertIn(expected, source)

    def test_revision_declares_foreign_keys_and_key_checks(self) -> None:
        source = (VERSIONS_ROOT / "20260729_0001_foundation_schema.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ondelete=\"RESTRICT\"", source)
        self.assertIn("ck_experience_candidate_source", source)
        self.assertIn("ck_behavior_event_failure_code", source)

    def test_ai_schema_revision_has_all_six_fields_and_safe_downgrade(self) -> None:
        source = (VERSIONS_ROOT / "20260729_0002_ai_schema_0_1_3.py").read_text(
            encoding="utf-8"
        )
        for column in (
            "target_snapshot_hash",
            "command_id",
            "capability_fingerprint",
            "cost_source",
            "pricing_version",
            "provider_error_class",
        ):
            self.assertIn(f'"{column}"', source)
        self.assertIn("idx_ai_task_command_id", source)
        self.assertIn("idx_ai_call_provider_error_class", source)
        self.assertIn("ck_ai_call_cost_source", source)
        self.assertIn("ck_ai_call_calculated_pricing", source)
        self.assertIn("Refusing lossy downgrade", source)

    def test_ai_schema_revision_does_not_fabricate_backfill_values(self) -> None:
        source = (VERSIONS_ROOT / "20260729_0002_ai_schema_0_1_3.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("UPDATE `ai_task`", source)
        self.assertNotIn("UPDATE `ai_call`", source)

    def test_refresh_rotation_delta_matches_review_decision(self) -> None:
        delta = json.loads(SPRINT1_DELTA_PATH.read_text(encoding="utf-8"))
        session = delta["tables"]["user_session"]
        self.assertTrue(session["alter"]["revoked_at"]["nullable"])
        self.assertEqual(session["add"]["token_family_id"]["backfill"], "session_public_id")
        self.assertFalse(session["add"]["token_family_id"]["nullable"])
        self.assertEqual(
            session["add"]["replaced_by_session_id"]["foreign_key"], "user_session.id"
        )
        indexes = {index["name"]: index for index in session["indexes"]}
        self.assertTrue(indexes["uk_user_session_replaced_by"]["unique"])
        self.assertEqual(
            indexes["idx_session_family_state"]["columns"],
            ["token_family_id", "revoked_at", "expires_at", "id"],
        )

    def test_sprint1_delta_catalogs_all_six_ai_fields(self) -> None:
        delta = json.loads(SPRINT1_DELTA_PATH.read_text(encoding="utf-8"))["tables"]
        self.assertEqual(
            set(delta["ai_task"]["add"]), {"target_snapshot_hash", "command_id"}
        )
        self.assertEqual(
            set(delta["ai_call"]["add"]),
            {"capability_fingerprint", "cost_source", "pricing_version", "provider_error_class"},
        )
        self.assertEqual(delta["ai_task"]["add"]["command_id"]["collation"], "ascii_bin")

    def test_refresh_rotation_migration_has_safe_backfill_and_downgrade_guard(self) -> None:
        source = (VERSIONS_ROOT / "20260729_0003_refresh_token_rotation.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "SET `token_family_id` = `session_public_id`", source
        )
        self.assertIn("uk_user_session_replaced_by", source)
        self.assertIn("fk_user_session_replaced_by_session_id", source)
        self.assertIn("idx_session_family_state", source)
        self.assertIn("`revoked_at` IS NULL", source)
        self.assertIn("`rotated_at` IS NOT NULL", source)
        self.assertIn("Refusing lossy downgrade", source)

    def test_file_finalization_revision_persists_storage_version_and_protects_downgrade(self) -> None:
        source = (VERSIONS_ROOT / "20260729_0004_file_object_finalization.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("storage_version_id", source)
        self.assertIn("idx_file_storage_version", source)
        self.assertIn("Refusing lossy downgrade", source)

    def test_prd_source_revision_is_the_only_frozen_additive_delta(self) -> None:
        source = (VERSIONS_ROOT / "20260821_0005_prd_source_requirement_version.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("op.add_column("), 1)
        self.assertEqual(source.count("op.create_index("), 1)
        self.assertEqual(source.count("op.create_foreign_key("), 1)
        self.assertIn('"source_requirement_version_id"', source)
        self.assertIn('mysql.BIGINT(unsigned=True)', source)
        self.assertIn('nullable=False', source)
        self.assertIn('"idx_prd_source_requirement_version"', source)
        self.assertIn('"fk_prd_source_requirement_version_id"', source)
        self.assertIn('"requirement_version"', source)
        self.assertIn('ondelete="RESTRICT"', source)
        self.assertIn('onupdate="RESTRICT"', source)
        self.assertNotIn("UPDATE `prd`", source)
        self.assertIn("Refusing lossy downgrade", source)

    def test_prd_source_revision_imports_and_downgrade_is_fail_closed(self) -> None:
        path = VERSIONS_ROOT / "20260821_0005_prd_source_requirement_version.py"
        spec = importlib.util.spec_from_file_location("prd_source_revision", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Result:
            def __init__(self, count: int) -> None:
                self.count = count

            def scalar_one(self) -> int:
                return self.count

        class Bind:
            def __init__(self, count: int) -> None:
                self.count = count

            def execute(self, _statement):
                return Result(self.count)

        class Operations:
            def __init__(self, count: int) -> None:
                self.bind = Bind(count)
                self.calls: list[tuple] = []

            def get_bind(self):
                return self.bind

            def drop_constraint(self, *args, **kwargs) -> None:
                self.calls.append(("constraint", args, kwargs))

            def drop_index(self, *args, **kwargs) -> None:
                self.calls.append(("index", args, kwargs))

            def drop_column(self, *args, **kwargs) -> None:
                self.calls.append(("column", args, kwargs))

        populated = Operations(1)
        module.op = populated
        with self.assertRaisesRegex(RuntimeError, "PRD data exists"):
            module.downgrade()
        self.assertEqual(populated.calls, [])

        empty = Operations(0)
        module.op = empty
        module.downgrade()
        self.assertEqual([call[0] for call in empty.calls], ["constraint", "index", "column"])
