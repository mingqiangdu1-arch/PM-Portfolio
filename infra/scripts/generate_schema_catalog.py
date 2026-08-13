from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "数据埋点与数据库设计" / "数据字典.md"
OUTPUT = ROOT / "infra" / "migrations" / "schema_catalog.json"

TYPE_PATTERN = re.compile(
    r"^([a-z0-9_/]+) "
    r"(BIGINT UNSIGNED|SMALLINT UNSIGNED|INT UNSIGNED|VARCHAR\(\d+\)|CHAR\(\d+\)|"
    r"DATETIME\(6\)|DECIMAL\(\d+,\d+\)|BOOLEAN|MEDIUMTEXT|TEXT|JSON)(.*)$"
)
INDEX_PATTERN = re.compile(r"`((?:uk|idx)_[a-z0-9_]+)\(([^)]+)\)`")
SINGLE_COLUMN_UNIQUES = {
    "user_session": {
        "uk_session_public_id": "session_public_id",
        "uk_refresh_hash": "refresh_token_hash",
    }
}

COMMON_GROUPS = {
    "identity",
    "created",
    "mutable",
    "archivable",
    "retained",
    "record_status",
    "result_status",
    "adoption_status",
    "modification_intensity",
    "privacy_class",
    "data_phase",
    "quality_status",
}
TABLE_NAMES = {
    "user_account", "user_session", "project_member", "project", "project_version",
    "project_context", "version_change_record", "stored_file", "file_version",
    "file_relation", "file_parse_result", "requirement", "requirement_version", "prd",
    "prd_version", "flow_decision", "flow", "flow_version", "flow_export",
    "design_review", "design_review_scope", "review_feedback",
    "review_feedback_disposition", "implementation_plan", "implementation_plan_version",
    "confirmation_round", "confirmation_material", "difference_record",
    "readiness_check_result", "test_record", "test_evidence", "issue", "bug_detail",
    "optimization_detail", "issue_disposition", "model_catalog", "provider_profile",
    "skill", "skill_version", "prompt", "prompt_version", "template", "template_version",
    "context_strategy", "context_strategy_version", "ai_task", "ai_call",
    "ai_context_usage", "ai_result", "ai_evaluation", "ai_adoption", "behavior_event",
    "business_event_outbox", "ai_event_outbox", "event_compensation",
    "event_ingest_rejection", "operation_audit_log", "idempotency_record",
    "retention_policy", "metric_definition", "metric_snapshot", "data_quality_run",
    "data_quality_issue", "optimization_evaluation", "optimization_metric_result",
    "experience_candidate", "experience", "experience_version",
    "experience_project_relation", "scenario", "checklist", "checklist_version",
    "knowledge_usage", "knowledge_index_record", "experiment_definition",
    "experiment_assignment", "data_purge_run",
}
EVENT_FIELDS = {
    "event_id": ("VARCHAR(64)", False),
    "event_name": ("VARCHAR(128)", False),
    "schema_version": ("VARCHAR(16)", False),
    "occurred_at": ("DATETIME(6)", False),
    "ingested_at": ("DATETIME(6)", False),
    "user_id": ("BIGINT UNSIGNED", True),
    "session_id": ("VARCHAR(64)", True),
    "project_id": ("BIGINT UNSIGNED", True),
    "project_version_id": ("BIGINT UNSIGNED", True),
    "module": ("VARCHAR(32)", False),
    "object_type": ("VARCHAR(64)", True),
    "object_id": ("BIGINT UNSIGNED", True),
    "object_version_id": ("BIGINT UNSIGNED", True),
    "ai_task_id": ("BIGINT UNSIGNED", True),
    "ai_call_id": ("BIGINT UNSIGNED", True),
    "result_status": ("VARCHAR(32)", False),
    "failure_code": ("VARCHAR(64)", True),
    "source_type": ("VARCHAR(32)", False),
    "trace_id": ("VARCHAR(64)", True),
    "command_id": ("VARCHAR(64)", True),
    "correlation_id": ("VARCHAR(64)", True),
    "causation_id": ("VARCHAR(64)", True),
    "product_release": ("VARCHAR(64)", True),
    "client_version": ("VARCHAR(64)", True),
    "ai_capability_versions_json": ("JSON", True),
    "privacy_class": ("VARCHAR(32)", False),
    "payload_json": ("JSON", False),
}
OUTBOX_FIELDS = {
    "event_id": ("VARCHAR(64)", False),
    "aggregate_type": ("VARCHAR(64)", False),
    "aggregate_id": ("BIGINT UNSIGNED", False),
    "aggregate_version": ("BIGINT UNSIGNED", False),
    "event_name": ("VARCHAR(128)", False),
    "schema_version": ("VARCHAR(16)", False),
    "payload_json": ("JSON", False),
    "publish_status": ("VARCHAR(32)", False),
    "attempt_count": ("INT UNSIGNED", False),
    "next_attempt_at": ("DATETIME(6)", True),
    "published_at": ("DATETIME(6)", True),
}
GENERATED_EXPRESSIONS = {
    ("project_version", "current_project_key"): "CASE WHEN is_working = 1 THEN project_id END",
    ("requirement_version", "effective_owner_key"): "CASE WHEN is_effective = 1 THEN requirement_id END",
    ("prd", "main_prd_key"): "CASE WHEN is_main = 1 THEN project_version_id END",
    ("prd_version", "effective_owner_key"): "CASE WHEN is_effective = 1 THEN prd_id END",
    ("flow_decision", "current_prd_key"): "CASE WHEN is_current = 1 THEN prd_id END",
    ("flow_version", "effective_owner_key"): "CASE WHEN is_effective = 1 THEN flow_id END",
    ("implementation_plan_version", "effective_owner_key"): "CASE WHEN is_effective = 1 THEN implementation_plan_id END",
    ("confirmation_round", "effective_plan_key"): "CASE WHEN is_effective = 1 THEN implementation_plan_id END",
    ("skill_version", "current_owner_key"): "CASE WHEN is_current = 1 THEN skill_id END",
    ("prompt_version", "current_owner_key"): "CASE WHEN is_current = 1 THEN prompt_id END",
    ("template_version", "current_owner_key"): "CASE WHEN is_current = 1 THEN template_id END",
    ("context_strategy_version", "current_owner_key"): "CASE WHEN is_current = 1 THEN context_strategy_id END",
    ("ai_adoption", "initial_result_key"): "CASE WHEN supersedes_adoption_id IS NULL THEN ai_result_id END",
    ("metric_snapshot", "dimension_hash"): "SHA2(CAST(dimension_json AS CHAR), 256)",
    ("experience_version", "current_owner_key"): "CASE WHEN is_current = 1 THEN experience_id END",
    ("checklist_version", "current_owner_key"): "CASE WHEN is_current = 1 THEN checklist_id END",
}


def expand_names(group: str) -> list[str]:
    parts = group.split("/")
    if len(parts) == 1:
        return parts
    first = parts[0]
    prefix = first.rsplit("_", 1)[0] if "_" in first else ""
    return [first] + [f"{prefix}_{part}" if "_" not in part and prefix else part for part in parts[1:]]


def add_field(fields: dict[str, dict], name: str, sql_type: str, nullable: bool, generated: str | None = None) -> None:
    fields.setdefault(
        name,
        {"name": name, "type": sql_type, "nullable": nullable, "generated": generated},
    )


def common_fields(description: str) -> dict[str, dict]:
    fields: dict[str, dict] = {}
    if any(marker in description for marker in ("公共", "`id`", "与 Business Outbox 相同")):
        add_field(fields, "id", "BIGINT UNSIGNED", False)
    if "公共创建" in description or "公共可变" in description or "公共事件" in description:
        add_field(fields, "created_at", "DATETIME(6)", False)
        add_field(fields, "created_by", "BIGINT UNSIGNED", True)
    if "公共可变" in description:
        add_field(fields, "updated_at", "DATETIME(6)", False)
        add_field(fields, "updated_by", "BIGINT UNSIGNED", True)
        add_field(fields, "row_version", "BIGINT UNSIGNED", False)
    if "归档" in description:
        add_field(fields, "archived_at", "DATETIME(6)", True)
        add_field(fields, "archived_by", "BIGINT UNSIGNED", True)
    if "retained" in description:
        add_field(fields, "retention_class", "VARCHAR(32)", False)
        add_field(fields, "expires_at", "DATETIME(6)", True)
    return fields


def parse() -> dict:
    tables: list[dict] = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| `([a-z][a-z0-9_]+)` \|", line)
        if not match or match.group(1) not in TABLE_NAMES:
            continue
        name = match.group(1)
        parts = line.split(" | ")
        description = parts[2] if len(parts) >= 4 else parts[1]
        constraints = parts[3] if len(parts) >= 4 else parts[2]
        fields = common_fields(description)
        if name == "behavior_event":
            for field_name, (sql_type, nullable) in EVENT_FIELDS.items():
                add_field(fields, field_name, sql_type, nullable)
        if name in {"business_event_outbox", "ai_event_outbox"}:
            for field_name, (sql_type, nullable) in OUTBOX_FIELDS.items():
                add_field(fields, field_name, sql_type, nullable)
            add_field(fields, "created_at", "DATETIME(6)", False)
        for fragment in re.findall(r"`([^`]+)`", description):
            typed = TYPE_PATTERN.match(fragment)
            if not typed:
                continue
            names, sql_type, flags = typed.groups()
            nullable = "NULL" in flags and "NN" not in flags
            for field_name in expand_names(names):
                generated = GENERATED_EXPRESSIONS.get((name, field_name))
                add_field(fields, field_name, sql_type, nullable or generated is not None, generated)
        if "id" not in fields:
            add_field(fields, "id", "BIGINT UNSIGNED", False)
        indexes = []
        for index_name, columns in INDEX_PATTERN.findall(line):
            indexes.append(
                {
                    "name": index_name,
                    "unique": index_name.startswith("uk_"),
                    "columns": [column.strip() for column in columns.split(",")],
                }
            )
        existing_index_names = {index["name"] for index in indexes}
        for index_name, column in SINGLE_COLUMN_UNIQUES.get(name, {}).items():
            if index_name not in existing_index_names:
                indexes.append(
                    {"name": index_name, "unique": True, "columns": [column]}
                )
        tables.append({"name": name, "fields": list(fields.values()), "indexes": indexes})
    if len(tables) != 77:
        raise RuntimeError(f"Expected 77 table definitions, found {len(tables)}")
    return {
        "catalog_version": "2026-07-29.candidate.1",
        "source": "数据埋点与数据库设计/数据字典.md",
        "review_required": ["ai-data", "review"],
        "tables": tables,
    }


def main() -> None:
    catalog = parse()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(catalog['tables'])} table definitions at {OUTPUT}")


if __name__ == "__main__":
    main()
