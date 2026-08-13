import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


AI_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ROOT = AI_ROOT / "contracts" / "candidates" / "m2-requirement-clarification"
FORMAL_ROOT = AI_ROOT / "schemas" / "v0.2"
PREVIOUS_R2_BUNDLE_HASH = "ce70eda604ced1291f838ccb880d041a164b51c2aac586520681cbf856f88c5d"
R3_IMPLEMENTATION_BUNDLE_HASH = "479102227d77d6e93d3d091e2012fb68f437748fec2f47cafe55c08071c74d39"
R4_IMPLEMENTATION_BUNDLE_HASH = "feaf27e63ffc45e18b10ab3db0332531d2fb410a7ac207c9af15387378ca10d6"
SCHEMA_FILES = (
    "requirement-clarify-task-envelope.schema.json",
    "requirement-clarify-result-content.schema.json",
    "context-snapshot-0.2.schema.json",
    "requirement-content.schema.json",
    "requirement-business-event-0.2.schema.json",
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        load(FORMAL_ROOT / name),
        format_checker=FormatChecker(),
    )


def test_frozen_candidate_hash_and_exact_formal_promotion() -> None:
    rows = []
    for path in sorted(item for item in CANDIDATE_ROOT.rglob("*") if item.is_file() and "__pycache__" not in item.parts):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{path.relative_to(CANDIDATE_ROOT).as_posix()}={digest}")
    bundle_hash = hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()
    assert len(rows) == 15
    assert bundle_hash == R3_IMPLEMENTATION_BUNDLE_HASH
    for name in SCHEMA_FILES:
        if name == "requirement-content.schema.json":
            continue
        assert (FORMAL_ROOT / name).read_bytes() == (CANDIDATE_ROOT / name).read_bytes()
    r3 = load(CANDIDATE_ROOT / "requirement-content.schema.json")
    expected_r4 = deepcopy(r3)
    expected_r4["properties"]["clarification"]["properties"]["continue_deep_confirmed"] = {
        "type": "boolean",
        "default": False,
        "description": "Historical content without this field is consumed as false.",
    }
    assert load(FORMAL_ROOT / "requirement-content.schema.json") == expected_r4


def test_r4_continue_deep_confirmation_is_optional_boolean_only() -> None:
    content = load(CANDIDATE_ROOT / "fixed-samples" / "valid.json")["requirement_content"]
    validator("requirement-content.schema.json").validate(content)
    for value in (False, True):
        candidate = deepcopy(content)
        candidate["clarification"]["continue_deep_confirmed"] = value
        validator("requirement-content.schema.json").validate(candidate)
    invalid = deepcopy(content)
    invalid["clarification"]["continue_deep_confirmed"] = "true"
    errors = list(validator("requirement-content.schema.json").iter_errors(invalid))
    assert errors and any(error.validator == "type" for error in errors)


def test_manifest_publishes_v02_and_preserves_v013_compatibility() -> None:
    manifest = load(AI_ROOT / "schemas" / "schema-manifest.json")
    assert manifest["candidate_version"] == "0.1.3"
    assert manifest["current_schema_version"] == "0.2.0"
    assert manifest["previous_r2_bundle_sha256_audit_only"] == PREVIOUS_R2_BUNDLE_HASH
    assert manifest["previous_r3_bundle_sha256_audit_only"] == R3_IMPLEMENTATION_BUNDLE_HASH
    assert manifest["implementation_candidate_bundle_algorithm"] == (
        "sha256 of UTF-8 LF-terminated sorted basename=sha256(file_bytes) rows for schema_versions[0.2.0] files"
    )
    rows = []
    for schema_path in sorted(manifest["schema_versions"]["0.2.0"], key=lambda item: Path(item).name):
        name = Path(schema_path).name
        digest = hashlib.sha256((AI_ROOT / "schemas" / schema_path).read_bytes()).hexdigest()
        rows.append(f"{name}={digest}")
    bundle_hash = hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()
    assert bundle_hash == R4_IMPLEMENTATION_BUNDLE_HASH
    assert manifest["implementation_candidate_bundle_sha256"] == R4_IMPLEMENTATION_BUNDLE_HASH
    assert manifest["historical_manifest_sha256"]["0.1.3"] == (
        "1685211f2e6e63d272f826d996b131cb04c7b364c3be5d20396550db4153c4ff"
    )
    assert len(manifest["schema_versions"]["0.1.3"]) == 9
    assert manifest["schema_versions"]["0.2.0"] == [f"v0.2/{name}" for name in SCHEMA_FILES]
    assert set(manifest["schemas"]) == {
        *manifest["schema_versions"]["0.1.3"],
        *manifest["schema_versions"]["0.2.0"],
    }


def test_v02_schemas_are_draft_202012_and_accept_frozen_positive_samples() -> None:
    for name in SCHEMA_FILES:
        Draft202012Validator.check_schema(load(FORMAL_ROOT / name))
    sample = load(CANDIDATE_ROOT / "fixed-samples" / "valid.json")
    validator("requirement-clarify-task-envelope.schema.json").validate(sample["task"])
    for result in sample["results"]:
        validator("requirement-clarify-result-content.schema.json").validate(result)
    validator("context-snapshot-0.2.schema.json").validate(sample["context_snapshot"])
    for event in sample["requirement_events"]:
        validator("requirement-business-event-0.2.schema.json").validate(event)
    validator("requirement-content.schema.json").validate(sample["requirement_content"])


def test_formal_requirement_content_matches_backend_public_shape() -> None:
    schema = load(FORMAL_ROOT / "requirement-content.schema.json")
    assert schema["properties"]["raw_input"]["readOnly"] is True
    assert schema["properties"]["raw_input_ref"]["readOnly"] is True
    assessment = schema["$defs"]["clarification_assessment"]
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
    dimension = schema["$defs"]["clarification_assessment_dimension"]
    assert set(dimension["required"]) == {"status", "missing_items", "source_refs"}
    assert set(dimension["properties"]) == set(dimension["required"])
    round_properties = schema["$defs"]["clarification_round"]["properties"]
    assert (round_properties["questions"]["minItems"], round_properties["questions"]["maxItems"]) == (1, 3)
    assert (round_properties["answers"]["minItems"], round_properties["answers"]["maxItems"]) == (1, 3)
