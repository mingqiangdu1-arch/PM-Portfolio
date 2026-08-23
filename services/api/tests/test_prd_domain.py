from __future__ import annotations

import copy
import unittest

from app.modules.prds.domain import (
    DesignReviewStatus,
    PrdContentValidationError,
    PrdStatus,
    ReviewDecision,
    validate_prd_content,
)


def valid_content() -> dict:
    return {
        "schema_version": "prd.mvp2.v1",
        "background": "Background",
        "goal": "Goal",
        "primary_user": "Owner",
        "in_scope": ["One"],
        "out_of_scope": ["Two"],
        "core_workflow": ["Three"],
        "key_rules": ["Four"],
        "exceptions_and_boundaries": [],
        "acceptance_criteria": ["Five"],
    }


class PrdDomainFoundationTests(unittest.TestCase):
    def test_frozen_enumerations_have_no_extra_states(self) -> None:
        self.assertEqual(
            [value.value for value in PrdStatus],
            ["draft", "in_review", "changes_requested", "confirmed"],
        )
        self.assertEqual(
            [value.value for value in DesignReviewStatus],
            ["open", "changes_requested", "passed"],
        )
        self.assertEqual(
            [value.value for value in ReviewDecision],
            ["changes_requested", "pass"],
        )

    def test_validator_normalizes_nfc_crlf_and_edges(self) -> None:
        content = valid_content()
        content["background"] = "  e\u0301\r\nline  "
        content["in_scope"] = ["  item  "]
        normalized = validate_prd_content(content)
        self.assertEqual(normalized["background"], "é\nline")
        self.assertEqual(normalized["in_scope"], ["item"])

    def test_validator_rejects_unknown_missing_null_blank_and_wrong_schema(self) -> None:
        candidates = []
        unknown = valid_content()
        unknown["extra"] = "forbidden"
        candidates.append(unknown)
        missing = valid_content()
        del missing["goal"]
        candidates.append(missing)
        null_value = valid_content()
        null_value["goal"] = None
        candidates.append(null_value)
        blank = valid_content()
        blank["acceptance_criteria"] = ["  "]
        candidates.append(blank)
        wrong_schema = valid_content()
        wrong_schema["schema_version"] = "prd.future"
        candidates.append(wrong_schema)
        empty_required = valid_content()
        empty_required["core_workflow"] = []
        candidates.append(empty_required)

        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(
                PrdContentValidationError
            ):
                validate_prd_content(candidate)

    def test_validator_rejects_normalized_duplicates(self) -> None:
        for duplicate in (["e\u0301", "é"], [" item ", "item"]):
            content = copy.deepcopy(valid_content())
            content["key_rules"] = duplicate
            with self.subTest(duplicate=duplicate), self.assertRaises(
                PrdContentValidationError
            ):
                validate_prd_content(content)


if __name__ == "__main__":
    unittest.main()
