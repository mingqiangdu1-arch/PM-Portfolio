"""Lint candidate JSON Schemas and validate bundled examples."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas" / "v0.1"
EXAMPLE_FILE = ROOT / "examples" / "events" / "valid-events.json"
SPRINT1_EXAMPLE_FILE = ROOT / "examples" / "events" / "sprint1-valid-events.json"


def load_schemas() -> dict[str, dict]:
    schemas = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(document)
        schemas[path.name] = document
    return schemas


def validate_examples(schemas: dict[str, dict]) -> None:
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    validators = [
        Draft202012Validator(
            schemas[name],
            registry=registry,
            format_checker=FormatChecker(),
        )
        for name in ("event-envelope.schema.json", "ai-outbox-event.schema.json")
    ]
    examples = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))
    for index, event in enumerate(examples):
        for validator in validators:
            errors = sorted(validator.iter_errors(event), key=lambda item: list(item.path))
            if errors:
                rendered = "; ".join(error.message for error in errors)
                raise ValueError(f"event example {index} invalid: {rendered}")
    sprint1_validator = Draft202012Validator(
        schemas["sprint1-business-event.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )
    for index, event in enumerate(json.loads(SPRINT1_EXAMPLE_FILE.read_text(encoding="utf-8"))):
        errors = sorted(sprint1_validator.iter_errors(event), key=lambda item: list(item.path))
        if errors:
            rendered = "; ".join(error.message for error in errors)
            raise ValueError(f"Sprint 1 event example {index} invalid: {rendered}")


def main() -> None:
    schemas = load_schemas()
    validate_examples(schemas)
    print(f"validated {len(schemas)} schemas and bundled event examples")


if __name__ == "__main__":
    main()
