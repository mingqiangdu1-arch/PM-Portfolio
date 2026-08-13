from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from app.integrations.result_storage import canonical_json

def validate_result_content(result: dict[str, Any]) -> bytes:
    schema_path = Path(__file__).parents[2] / "schemas" / "v0.2" / "requirement-clarify-result-content.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
    return canonical_json(result)

def validate_context_snapshot(snapshot: dict[str, Any]) -> None:
    schema_path = Path(__file__).parents[2] / "schemas" / "v0.2" / "context-snapshot-0.2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(snapshot)
