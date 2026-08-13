"""Create the 77-table foundation schema candidate.

Revision ID: 20260729_0001
Revises: None
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "20260729_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATALOG_PATH = Path(__file__).resolve().parents[1] / "schema_catalog.json"
FK_TARGETS = {
    "user_id": "user_account",
    "owner_user_id": "user_account",
    "actor_user_id": "user_account",
    "evaluator_user_id": "user_account",
    "reviewed_by": "user_account",
    "decided_by": "user_account",
    "submitted_by": "user_account",
    "passed_by": "user_account",
    "confirmed_by": "user_account",
    "tester_id": "user_account",
    "assignee_id": "user_account",
    "responsible_user_id": "user_account",
    "approved_by": "user_account",
    "created_by": "user_account",
    "updated_by": "user_account",
    "archived_by": "user_account",
    "project_id": "project",
    "project_version_id": "project_version",
    "target_project_version_id": "project_version",
    "from_version_id": "project_version",
    "to_version_id": "project_version",
    "stored_file_id": "stored_file",
    "file_version_id": "file_version",
    "drawio_file_version_id": "file_version",
    "requirement_id": "requirement",
    "prd_id": "prd",
    "flow_id": "flow",
    "design_review_id": "design_review",
    "scope_id": "design_review_scope",
    "review_feedback_id": "review_feedback",
    "implementation_plan_id": "implementation_plan",
    "plan_version_id": "implementation_plan_version",
    "review_id": "design_review",
    "confirmation_round_id": "confirmation_round",
    "test_record_id": "test_record",
    "issue_id": "issue",
    "source_issue_id": "issue",
    "model_catalog_id": "model_catalog",
    "provider_profile_id": "provider_profile",
    "skill_id": "skill",
    "skill_version_id": "skill_version",
    "prompt_id": "prompt",
    "prompt_version_id": "prompt_version",
    "template_id": "template",
    "template_version_id": "template_version",
    "context_strategy_id": "context_strategy",
    "context_strategy_version_id": "context_strategy_version",
    "ai_task_id": "ai_task",
    "ai_call_id": "ai_call",
    "source_ai_call_id": "ai_call",
    "ai_result_id": "ai_result",
    "metric_definition_id": "metric_definition",
    "data_quality_run_id": "data_quality_run",
    "optimization_evaluation_id": "optimization_evaluation",
    "experience_id": "experience",
    "source_candidate_id": "experience_candidate",
    "scenario_id": "scenario",
    "checklist_id": "checklist",
    "retention_policy_id": "retention_policy",
    "experiment_definition_id": "experiment_definition",
}
CHECKS = {
    "behavior_event": [
        ("ck_behavior_event_failure_code", "result_status <> 'failed' OR failure_code IS NOT NULL"),
    ],
    "experience_candidate": [
        ("ck_experience_candidate_source", "source_issue_id IS NOT NULL OR source_ai_call_id IS NOT NULL"),
    ],
    "project_version": [
        ("ck_project_version_working", "is_working IN (0, 1)"),
    ],
}


def _type(sql_type: str) -> sa.types.TypeEngine:
    if sql_type == "BIGINT UNSIGNED":
        return mysql.BIGINT(unsigned=True)
    if sql_type == "INT UNSIGNED":
        return mysql.INTEGER(unsigned=True)
    if sql_type == "SMALLINT UNSIGNED":
        return mysql.SMALLINT(unsigned=True)
    if sql_type == "BOOLEAN":
        return sa.Boolean()
    if sql_type == "TEXT":
        return sa.Text()
    if sql_type == "MEDIUMTEXT":
        return mysql.MEDIUMTEXT()
    if sql_type == "JSON":
        return mysql.JSON()
    if sql_type == "DATETIME(6)":
        return mysql.DATETIME(fsp=6)
    if sql_type.startswith("VARCHAR("):
        return sa.String(int(sql_type[8:-1]))
    if sql_type.startswith("CHAR("):
        return sa.CHAR(int(sql_type[5:-1]))
    if sql_type.startswith("DECIMAL("):
        precision, scale = (int(value) for value in sql_type[8:-1].split(","))
        return sa.Numeric(precision, scale)
    raise ValueError(f"Unsupported catalog type: {sql_type}")


def _catalog() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if len(catalog["tables"]) != 77:
        raise RuntimeError("Foundation catalog must contain exactly 77 tables")
    return catalog


def _column(field: dict) -> sa.Column:
    kwargs: dict = {"nullable": field["nullable"]}
    if field["name"] == "id":
        kwargs.update(primary_key=True, autoincrement=True)
    if field["name"] in {"row_version", "attempt_count"}:
        kwargs["server_default"] = sa.text("1" if field["name"] == "row_version" else "0")
    positional = []
    if field.get("generated"):
        positional.append(sa.Computed(field["generated"], persisted=True))
    return sa.Column(field["name"], _type(field["type"]), *positional, **kwargs)


def upgrade() -> None:
    catalog = _catalog()
    table_names = {table["name"] for table in catalog["tables"]}
    for table in catalog["tables"]:
        columns = [_column(field) for field in table["fields"]]
        constraints = [
            sa.UniqueConstraint(*index["columns"], name=index["name"])
            for index in table["indexes"]
            if index["unique"]
        ]
        constraints.extend(
            sa.CheckConstraint(expression, name=name)
            for name, expression in CHECKS.get(table["name"], [])
        )
        op.create_table(
            table["name"],
            *columns,
            *constraints,
            mysql_engine="InnoDB",
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_0900_ai_ci",
        )
        for index in table["indexes"]:
            if not index["unique"]:
                op.create_index(index["name"], table["name"], index["columns"])
    for table in catalog["tables"]:
        for field in table["fields"]:
            target = FK_TARGETS.get(field["name"])
            if target not in table_names or field["name"] == "id":
                continue
            constraint_name = f"fk_{table['name']}_{field['name']}"[:60]
            op.create_foreign_key(
                constraint_name,
                table["name"],
                target,
                [field["name"]],
                ["id"],
                ondelete="RESTRICT",
                onupdate="RESTRICT",
            )


def downgrade() -> None:
    catalog = _catalog()
    table_names = {table["name"] for table in catalog["tables"]}
    for table in catalog["tables"]:
        for field in table["fields"]:
            target = FK_TARGETS.get(field["name"])
            if target not in table_names or field["name"] == "id":
                continue
            constraint_name = f"fk_{table['name']}_{field['name']}"[:60]
            op.drop_constraint(constraint_name, table["name"], type_="foreignkey")
    for table in reversed(catalog["tables"]):
        op.drop_table(table["name"])
