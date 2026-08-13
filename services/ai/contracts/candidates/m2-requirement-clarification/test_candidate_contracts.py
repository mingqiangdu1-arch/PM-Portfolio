import copy
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
AI_ROOT = ROOT.parents[2]
SCHEMAS = {
    "requirement-clarify-task-envelope.schema.json": "task",
    "requirement-clarify-result-content.schema.json": "results",
    "context-snapshot-0.2.schema.json": "context_snapshot",
    "requirement-content.schema.json": None,
    "requirement-business-event-0.2.schema.json": "requirement_events",
}
DIMENSION_KEYS = [
    "goal",
    "users_and_roles",
    "usage_scenarios",
    "functional_scope",
    "business_rules",
    "exception_cases",
    "permission_requirements",
    "acceptance_criteria",
]
SOURCE_REF_FIELDS = {
    "source_type",
    "source_id",
    "source_version_id",
    "content_hash",
    "label",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema, instance):
    return list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance)
    )


def pointer_parts(pointer):
    if pointer == "/":
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.lstrip("/").split("/")]


def get_pointer(document, pointer):
    current = document
    for part in pointer_parts(pointer):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def materialize_invalid(fixture, valid):
    instance = copy.deepcopy(get_pointer(valid, fixture["valid_pointer"]))
    for mutation in fixture["mutations"]:
        parts = pointer_parts(mutation["path"])
        parent = instance
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        leaf = parts[-1]
        if mutation.get("operation") == "remove":
            parent.pop(int(leaf)) if isinstance(parent, list) else parent.pop(leaf)
            continue
        value = (
            copy.deepcopy(get_pointer(valid, mutation["value_from"]))
            if "value_from" in mutation
            else copy.deepcopy(mutation["value"])
        )
        if isinstance(parent, list) and leaf == "-":
            parent.append(value)
        elif isinstance(parent, list):
            parent[int(leaf)] = value
        else:
            parent[leaf] = value
    return instance


def error_pointer(error):
    parts = [str(part) for part in error.absolute_path]
    return "/" + "/".join(parts) if parts else "/"


def test_manifest_is_complete_non_effective_and_ready_for_review():
    manifest = load(ROOT / "candidate-manifest.json")
    assert manifest["candidate_version"] == "0.2.0-proposed"
    assert manifest["schema_identity"] == "0.2.0"
    assert manifest["status"] == "ready_for_review"
    assert manifest["effective"] is False
    assert manifest["runtime_authorized"] is False
    assert manifest["formal_schema_history_preserved"] == "0.1.3"
    assert manifest["dimension_keys"] == DIMENSION_KEYS
    assert manifest["adoption_mapping"] == {
        "adopt": "adopted",
        "modified_adopt": "adopted_after_edit",
        "reject": "rejected",
    }
    assert manifest["derived_when_no_adoption_record"] == "not_reviewed"
    assert set(manifest["artifacts"]) == {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_draft_202012_schemas_and_all_positive_samples():
    schemas = {name: load(ROOT / name) for name in SCHEMAS}
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)

    valid = load(ROOT / "fixed-samples" / "valid.json")
    assert not validate(schemas["requirement-clarify-task-envelope.schema.json"], valid["task"])
    for result in valid["results"]:
        assert not validate(schemas["requirement-clarify-result-content.schema.json"], result)
    assert not validate(schemas["context-snapshot-0.2.schema.json"], valid["context_snapshot"])
    for event in valid["requirement_events"]:
        assert not validate(schemas["requirement-business-event-0.2.schema.json"], event)
    requirement_content = valid["requirement_content"]
    assert not validate(schemas["requirement-content.schema.json"], requirement_content)
    assert requirement_content["raw_input"] == (
        "用户原始输入：需要在 AI 不可用时保留人工编辑、回答与确认路径。\n"
        "原文中的换行、标点与大小写必须无损保留。"
    )


def test_requirement_content_rejects_lossy_or_legacy_public_shapes():
    schema = load(ROOT / "requirement-content.schema.json")
    valid = load(ROOT / "fixed-samples" / "valid.json")["requirement_content"]

    empty_raw_input = copy.deepcopy(valid)
    empty_raw_input["raw_input"] = ""
    assert any(error.validator == "minLength" for error in validate(schema, empty_raw_input))

    missing_raw_input = copy.deepcopy(valid)
    missing_raw_input.pop("raw_input")
    assert any(error.validator == "required" for error in validate(schema, missing_raw_input))

    legacy_flat_round = copy.deepcopy(valid)
    clarification = legacy_flat_round["clarification"]
    clarification["round_no"] = clarification["rounds"][0]["round_no"]
    clarification["questions"] = clarification["rounds"][0]["questions"]
    clarification["answers"] = clarification["rounds"][0]["answers"]
    clarification.pop("rounds")
    errors = validate(schema, legacy_flat_round)
    assert any(error.validator == "required" for error in errors)
    assert any(error.validator == "additionalProperties" for error in errors)


def test_requirement_content_matches_backend_readonly_assessment_and_round_bounds():
    schema = load(ROOT / "requirement-content.schema.json")
    properties = schema["properties"]
    assert properties["raw_input"]["readOnly"] is True
    assert properties["raw_input_ref"]["readOnly"] is True

    assessment = schema["$defs"]["clarification_assessment"]
    assert assessment["additionalProperties"] is False
    assert set(assessment["required"]) == {
        "assessment_version",
        "dimensions",
        "complexity_band",
        "complexity_reason",
        "recommended_mode",
        "missing_dimensions",
        "source_refs",
        "ai_result_id",
    }
    assert set(assessment["properties"]) == set(assessment["required"])
    assert assessment["properties"]["source_refs"] == {
        "$ref": "#/$defs/clarification_source_refs"
    }
    assert schema["properties"]["clarification"]["properties"]["assessment"] == {
        "anyOf": [
            {"$ref": "#/$defs/clarification_assessment"},
            {"type": "null"},
        ]
    }

    round_properties = schema["$defs"]["clarification_round"]["properties"]
    for name in ("questions", "answers"):
        assert round_properties[name]["minItems"] == 1
        assert round_properties[name]["maxItems"] == 3

    dimensions = schema["$defs"]["clarification_assessment_dimensions"]
    assert list(dimensions["required"]) == DIMENSION_KEYS
    assert set(dimensions["properties"]) == set(DIMENSION_KEYS)
    dimension = schema["$defs"]["clarification_assessment_dimension"]
    assert set(dimension["required"]) == {"status", "missing_items", "source_refs"}
    assert set(dimension["properties"]) == set(dimension["required"])

    valid = load(ROOT / "fixed-samples" / "valid.json")["requirement_content"]
    ai_result_assessment = copy.deepcopy(valid)
    assessment_value = ai_result_assessment["clarification"]["assessment"]
    assessment_value["dimension_completeness"] = assessment_value.pop("dimensions")
    assessment_value["reasons"] = [assessment_value.pop("complexity_reason")]
    assessment_value["missing_items"] = assessment_value.pop("missing_dimensions")
    errors = validate(schema, ai_result_assessment)
    assert any(error.validator == "anyOf" for error in errors)


def test_all_negative_fixtures_fail_for_the_declared_reason():
    valid = load(ROOT / "fixed-samples" / "valid.json")
    fixtures = sorted((ROOT / "fixed-samples").glob("invalid-*.json"))
    assert len(fixtures) == 5
    for path in fixtures:
        fixture = load(path)
        schema = load(ROOT / fixture["schema"])
        instance = materialize_invalid(fixture, valid)
        errors = validate(schema, instance)
        assert errors, path.name
        assert any(
            error.validator == fixture["expected_validator"]
            and error_pointer(error) == fixture["expected_path"]
            for error in errors
        ), (path.name, [(error.validator, error_pointer(error), error.message) for error in errors])


def test_frozen_enums_baseline_mapping_and_event_ownership():
    task = load(ROOT / "requirement-clarify-task-envelope.schema.json")
    result = load(ROOT / "requirement-clarify-result-content.schema.json")
    requirement = load(ROOT / "requirement-content.schema.json")
    event = load(ROOT / "requirement-business-event-0.2.schema.json")
    manifest = load(ROOT / "candidate-manifest.json")

    assert task["properties"]["status"]["enum"] == manifest["task_statuses"]
    assert result["properties"]["status"]["enum"] == manifest["result_statuses"]
    assert result["properties"]["result_kind"]["enum"] == manifest["result_kinds"]
    assert list(result["$defs"]["baseline_dimensions"]["properties"]) == DIMENSION_KEYS
    assert list(requirement["$defs"]["baseline"]["properties"]["dimensions"]["properties"]) == DIMENSION_KEYS
    assert "adoption" not in result["properties"]
    assert event["properties"]["producer"]["const"] == "Business API"
    assert "ingested_at" not in event["properties"]


def test_structured_source_refs_match_backend_shape_everywhere():
    task = load(ROOT / "requirement-clarify-task-envelope.schema.json")
    result = load(ROOT / "requirement-clarify-result-content.schema.json")
    requirement = load(ROOT / "requirement-content.schema.json")
    valid = load(ROOT / "fixed-samples" / "valid.json")

    assert task["properties"]["source_ref_ids"]["items"]["type"] == "string"
    for source_ref in (result["$defs"]["source_ref"], requirement["$defs"]["source_ref"]):
        assert set(source_ref["required"]) == SOURCE_REF_FIELDS
        assert set(source_ref["properties"]) == SOURCE_REF_FIELDS
        assert source_ref["properties"]["source_version_id"]["type"] == ["string", "null"]
        assert source_ref["properties"]["content_hash"]["pattern"] == "^[a-f0-9]{64}$"

    def assert_named_source_refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "source_refs":
                    assert isinstance(child, list)
                    for item in child:
                        assert isinstance(item, dict)
                        assert set(item) == SOURCE_REF_FIELDS
                else:
                    assert_named_source_refs(child)
        elif isinstance(value, list):
            for child in value:
                assert_named_source_refs(child)

    for result_sample in valid["results"]:
        assert_named_source_refs(result_sample)
    assert_named_source_refs(valid["requirement_content"])

    requirement_content = valid["requirement_content"]
    assert set(requirement_content["raw_input_ref"]) == SOURCE_REF_FIELDS
    assert set(requirement["$defs"]["question"]["properties"]) == {
        "question_id", "dimension", "question_text", "reason", "source_refs"
    }
    assert set(requirement["$defs"]["answer"]["properties"]) == {"question_id", "answer"}
    assert set(requirement["$defs"]["clarification_round"]["required"]) == {
        "round_no", "ai_task_id", "ai_result_id", "questions", "answers"
    }


def test_no_unadjudicated_placeholder_or_old_dimension_key():
    placeholders = re.compile(
        "TO" + "DO|T" + "BD|x-review-" + "blocker|pending-m2-" + "contracts-frozen",
        re.IGNORECASE,
    )
    old_key = re.compile(r"\bexcept" + r"ions\b", re.IGNORECASE)
    for path in ROOT.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            text = path.read_text(encoding="utf-8")
            assert not placeholders.search(text), path
            if not path.name.startswith("invalid-"):
                assert not old_key.search(text), path


def test_formal_schema_013_minimum_regression():
    formal_manifest = load(AI_ROOT / "schemas" / "schema-manifest.json")
    assert formal_manifest["candidate_version"] == "0.1.3"
    formal_paths = sorted((AI_ROOT / "schemas" / "v0.1").glob("*.schema.json"))
    assert len(formal_paths) == 9
    for path in formal_paths:
        Draft202012Validator.check_schema(load(path))
