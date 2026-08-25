from __future__ import annotations

import unittest

from app.modules.validation.service import _classification
from app.platform.errors import ApiError


BUG = {
    "reproduce_steps": "submit the form",
    "expected_result": "saved",
    "actual_result": "error",
    "environment": {"name": "local"},
}
OPTIMIZATION = {
    "problem_evidence": "three repeated steps",
    "hypothesis": "combining them reduces effort",
    "expected_outcome": "one step",
    "impact_scope": "requirement editor",
    "need_new_version": True,
}


class ValidationRuleTests(unittest.TestCase):
    def test_issue_extensions_are_conditionally_required_and_exclusive(self) -> None:
        self.assertEqual(_classification("defect", BUG, None), (BUG, None))
        self.assertEqual(_classification("optimization", None, OPTIMIZATION), (None, OPTIMIZATION))
        self.assertEqual(_classification("feedback", None, None), (None, None))
        self.assertEqual(_classification("data_anomaly", None, None), (None, None))

        invalid = [
            ("defect", None, None),
            ("defect", BUG, OPTIMIZATION),
            ("optimization", None, None),
            ("feedback", BUG, None),
            ("data_anomaly", None, OPTIMIZATION),
        ]
        for issue_type, bug, optimization in invalid:
            with self.assertRaises(ApiError) as caught:
                _classification(issue_type, bug, optimization)
            self.assertEqual((caught.exception.code, caught.exception.http_status), ("VALIDATION_ERROR", 422))

    def test_extension_detail_rejects_unknown_or_invalid_fields(self) -> None:
        with self.assertRaisesRegex(ApiError, "bug_detail fields"):
            _classification("defect", {**BUG, "unknown": True}, None)
        with self.assertRaisesRegex(ApiError, "need_new_version"):
            _classification("optimization", None, {**OPTIMIZATION, "need_new_version": "yes"})


if __name__ == "__main__":
    unittest.main()
