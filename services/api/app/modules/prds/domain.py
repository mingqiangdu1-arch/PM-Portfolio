from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Any


PRD_SCHEMA_VERSION = "prd.mvp2.v1"
PRD_CONTENT_KEYS = (
    "schema_version",
    "background",
    "goal",
    "primary_user",
    "in_scope",
    "out_of_scope",
    "core_workflow",
    "key_rules",
    "exceptions_and_boundaries",
    "acceptance_criteria",
)
PRD_SCALAR_FIELDS = ("background", "goal", "primary_user")
PRD_ARRAY_FIELDS = (
    "in_scope",
    "out_of_scope",
    "core_workflow",
    "key_rules",
    "exceptions_and_boundaries",
    "acceptance_criteria",
)
PRD_NONEMPTY_ARRAY_FIELDS = frozenset(PRD_ARRAY_FIELDS) - {"exceptions_and_boundaries"}


class PrdStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    CONFIRMED = "confirmed"


class DesignReviewStatus(StrEnum):
    OPEN = "open"
    CHANGES_REQUESTED = "changes_requested"
    PASSED = "passed"


class ReviewDecision(StrEnum):
    CHANGES_REQUESTED = "changes_requested"
    PASS = "pass"


class PrdContentValidationError(ValueError):
    pass


def _normalize_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PrdContentValidationError(f"{field} must be a string")
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip()
    if not normalized:
        raise PrdContentValidationError(f"{field} must not be blank")
    return normalized


def validate_prd_content(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PrdContentValidationError("content must be an object")
    actual_keys = set(value)
    required_keys = set(PRD_CONTENT_KEYS)
    if actual_keys != required_keys:
        missing = sorted(required_keys - actual_keys)
        unknown = sorted(actual_keys - required_keys)
        raise PrdContentValidationError(
            f"content keys must match the fixed schema; missing={missing}; unknown={unknown}"
        )
    if value["schema_version"] != PRD_SCHEMA_VERSION:
        raise PrdContentValidationError(
            f"schema_version must equal {PRD_SCHEMA_VERSION}"
        )

    normalized: dict[str, Any] = {"schema_version": PRD_SCHEMA_VERSION}
    for field in PRD_SCALAR_FIELDS:
        normalized[field] = _normalize_text(value[field], field)
    for field in PRD_ARRAY_FIELDS:
        items = value[field]
        if not isinstance(items, list):
            raise PrdContentValidationError(f"{field} must be an array")
        if field in PRD_NONEMPTY_ARRAY_FIELDS and not items:
            raise PrdContentValidationError(f"{field} must contain at least one item")
        normalized_items = [
            _normalize_text(item, f"{field}[{index}]")
            for index, item in enumerate(items)
        ]
        if len(set(normalized_items)) != len(normalized_items):
            raise PrdContentValidationError(
                f"{field} must not contain normalized duplicates"
            )
        normalized[field] = normalized_items
    return normalized
