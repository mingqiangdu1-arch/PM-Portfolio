"""Idempotently seed the public MVP5 DeepSeek capability bundle for local demos.

The tool never reads or stores the provider credential. ``secret_ref`` points
to the runtime environment variable that the worker resolves separately.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


VERSION = "0.2.0"
SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _hash(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _one(cursor: Any, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return dict(row) if row else None


def _entity(
    cursor: Any,
    *,
    table: str,
    lookup_sql: str,
    lookup: tuple[Any, ...],
    insert_sql: str,
    values: tuple[Any, ...],
) -> int:
    row = _one(cursor, lookup_sql, lookup)
    if row:
        return int(row["id"])
    cursor.execute(insert_sql, values)
    return int(cursor.lastrowid)


def _current_version(
    cursor: Any,
    *,
    entity_table: str,
    version_table: str,
    entity_id: int,
    foreign_key: str,
    columns: str,
    values: tuple[Any, ...],
    expected_hash: str,
    accept_existing: bool = False,
) -> int:
    entity = _one(cursor, f"SELECT current_version_id FROM {entity_table} WHERE id=%s FOR UPDATE", (entity_id,))
    if entity is None:
        raise RuntimeError(f"{entity_table} disappeared during seed")
    row = _one(
        cursor,
        f"SELECT id,content_hash,is_current FROM {version_table} WHERE {foreign_key}=%s AND version_no=%s",
        (entity_id, VERSION),
    )
    if row:
        if not accept_existing and row["content_hash"] != expected_hash:
            raise RuntimeError(f"existing {version_table} {VERSION} content hash conflicts with MVP5")
        version_id = int(row["id"])
    else:
        if entity["current_version_id"] is not None:
            raise RuntimeError(f"{entity_table} already has a different current version")
        cursor.execute(
            f"INSERT INTO {version_table} (created_at,created_by,{foreign_key},version_no,{columns},content_hash,is_current) "
            f"VALUES (%s,NULL,%s,%s,{','.join(['%s'] * len(values))},%s,1)",
            (datetime.now(UTC), entity_id, VERSION, *values, expected_hash),
        )
        version_id = int(cursor.lastrowid)
    if entity["current_version_id"] not in {None, version_id}:
        raise RuntimeError(f"{entity_table} current version conflicts with MVP5")
    cursor.execute(
        f"UPDATE {version_table} SET is_current=(id=%s) WHERE {foreign_key}=%s",
        (version_id, entity_id),
    )
    cursor.execute(
        f"UPDATE {entity_table} SET current_version_id=%s,updated_at=%s,row_version=row_version+1 WHERE id=%s",
        (version_id, datetime.now(UTC), entity_id),
    )
    return version_id


def seed(connection: Any) -> dict[str, int]:
    cursor = connection.cursor()
    now = datetime.now(UTC)
    try:
        model_id = _entity(
            cursor,
            table="model_catalog",
            lookup_sql="SELECT id FROM model_catalog WHERE provider_code=%s AND model_code=%s AND archived_at IS NULL",
            lookup=("deepseek", "deepseek-v4-flash"),
            insert_sql="INSERT INTO model_catalog (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,provider_code,model_code,display_name,capability_json,status) VALUES (%s,NULL,%s,NULL,1,NULL,NULL,%s,%s,%s,%s,'active')",
            values=(now, now, "deepseek", "deepseek-v4-flash", "DeepSeek V4 Flash", _json({"chat_completions": True, "json_object": True, "thinking": False})),
        )
        profile_id = _entity(
            cursor,
            table="provider_profile",
            lookup_sql="SELECT id FROM provider_profile WHERE user_id IS NULL AND profile_name=%s AND config_version=%s AND archived_at IS NULL",
            lookup=("portfolio-mvp5-deepseek", VERSION),
            insert_sql="INSERT INTO provider_profile (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,user_id,provider_code,profile_name,base_url,secret_ref,runtime_config_json,config_version,status) VALUES (%s,NULL,%s,NULL,1,NULL,NULL,NULL,%s,%s,%s,%s,%s,%s,'active')",
            values=(now, now, "deepseek", "portfolio-mvp5-deepseek", "https://api.deepseek.com", "env:DEEPSEEK_API_KEY", _json({"model": "deepseek-v4-flash", "response_format": "json_object", "timeout_seconds": 60, "max_tokens": 4096}), VERSION),
        )
        skill_id = _entity(
            cursor,
            table="skill",
            lookup_sql="SELECT id FROM skill WHERE name=%s AND archived_at IS NULL",
            lookup=("requirement.clarify",),
            insert_sql="INSERT INTO skill (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,name,skill_type,source_type,source_ref,status,current_version_id) VALUES (%s,NULL,%s,NULL,1,NULL,NULL,%s,%s,%s,%s,'active',NULL)",
            values=(now, now, "requirement.clarify", "product_design", "builtin", "app.requirement_clarification"),
        )
        rule_text = "Generate candidate-only Requirement clarification facts for human review; never formalize business truth."
        skill_version_id = _current_version(
            cursor,
            entity_table="skill",
            version_table="skill_version",
            entity_id=skill_id,
            foreign_key="skill_id",
            columns="input_schema_ref,output_schema_ref,rule_text",
            values=("schemas/v0.2/requirement-clarify-task-envelope.schema.json", "schemas/v0.2/requirement-clarify-result-content.schema.json", rule_text),
            expected_hash=_hash(rule_text),
            accept_existing=True,
        )
        system_prompt = "Return exactly one valid JSON object. AI output is candidate-only and requires human confirmation."
        user_template = "Analyze the supplied requirement using the frozen eight-dimension Requirement clarification schema."
        variables: dict[str, Any] = {}
        prompt_id = _entity(
            cursor,
            table="prompt",
            lookup_sql="SELECT id FROM prompt WHERE skill_version_id=%s AND name=%s AND archived_at IS NULL",
            lookup=(skill_version_id, "requirement.clarify.deepseek"),
            insert_sql="INSERT INTO prompt (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,skill_version_id,name,status,current_version_id) VALUES (%s,NULL,%s,NULL,1,NULL,NULL,%s,%s,'active',NULL)",
            values=(now, now, skill_version_id, "requirement.clarify.deepseek"),
        )
        prompt_version_id = _current_version(
            cursor,
            entity_table="prompt",
            version_table="prompt_version",
            entity_id=prompt_id,
            foreign_key="prompt_id",
            columns="system_prompt,user_template,variables_json",
            values=(system_prompt, user_template, _json(variables)),
            expected_hash=_hash({"system_prompt": system_prompt, "user_template": user_template, "variables_json": variables}),
        )
        template_id = _entity(
            cursor,
            table="template",
            lookup_sql="SELECT id FROM template WHERE name=%s AND template_type=%s AND archived_at IS NULL",
            lookup=("requirement.clarify.result.0.2", "json_schema"),
            insert_sql="INSERT INTO template (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,name,template_type,source_type,status,current_version_id) VALUES (%s,NULL,%s,NULL,1,NULL,NULL,%s,%s,%s,'active',NULL)",
            values=(now, now, "requirement.clarify.result.0.2", "json_schema", "builtin"),
        )
        template_content = (SERVICE_ROOT / "schemas" / "v0.2" / "requirement-clarify-result-content.schema.json").read_text(encoding="utf-8")
        template_version_id = _current_version(
            cursor,
            entity_table="template",
            version_table="template_version",
            entity_id=template_id,
            foreign_key="template_id",
            columns="content_format,content,variables_json",
            values=("json_schema", template_content, _json({})),
            expected_hash=_hash(template_content),
            accept_existing=True,
        )
        strategy_id = _entity(
            cursor,
            table="context_strategy",
            lookup_sql="SELECT id FROM context_strategy WHERE name=%s AND task_type=%s AND archived_at IS NULL",
            lookup=("requirement.clarify.raw-input-only", "requirement.clarify"),
            insert_sql="INSERT INTO context_strategy (created_at,created_by,updated_at,updated_by,row_version,archived_at,archived_by,name,task_type,status,current_version_id) VALUES (%s,NULL,%s,NULL,1,NULL,NULL,%s,%s,'active',NULL)",
            values=(now, now, "requirement.clarify.raw-input-only", "requirement.clarify"),
        )
        required = {"source_types": ["manual", "requirement_version"], "min_injected": 1}
        optional: dict[str, Any] = {}
        limits = {"max_sources": 1, "max_tokens": 12000}
        compression = {"mode": "none"}
        strategy_version_id = _current_version(
            cursor,
            entity_table="context_strategy",
            version_table="context_strategy_version",
            entity_id=strategy_id,
            foreign_key="context_strategy_id",
            columns="skill_version_id,required_context_json,optional_context_json,limit_config_json,compression_policy_json",
            values=(skill_version_id, _json(required), _json(optional), _json(limits), _json(compression)),
            expected_hash=_hash({"required": required, "optional": optional, "limits": limits, "compression": compression}),
            accept_existing=True,
        )
        connection.commit()
        return {
            "model_id": model_id,
            "profile_id": profile_id,
            "skill_version_id": skill_version_id,
            "prompt_version_id": prompt_version_id,
            "template_version_id": template_version_id,
            "context_strategy_version_id": strategy_version_id,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _database_url() -> str:
    direct = os.getenv("AI_DATABASE_URL")
    file_name = os.getenv("AI_DATABASE_URL_FILE")
    if direct and file_name:
        raise RuntimeError("AI_DATABASE_URL and AI_DATABASE_URL_FILE are mutually exclusive")
    if file_name:
        direct = Path(file_name).read_text(encoding="utf-8").strip()
    if not direct:
        raise RuntimeError("AI_DATABASE_URL is required")
    return direct


def main() -> int:
    if os.getenv("AI_ENVIRONMENT", "local").strip().lower() != "local":
        raise RuntimeError("MVP5 capability seed is local-only")
    import pymysql

    parsed = urlparse(_database_url())
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path:
        raise RuntimeError("AI_DATABASE_URL must be a MySQL URL")
    connection = pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=unquote(parsed.path.lstrip("/")),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        seeded = seed(connection)
    finally:
        connection.close()
    print("MVP5 DeepSeek capability bundle is ready: " + ", ".join(sorted(seeded)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
