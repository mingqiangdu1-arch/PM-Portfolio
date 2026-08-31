import unittest

from app.modules.prds.service import _current_review
from app.platform.errors import ApiError


class _Result:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_Result":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows

    def first(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None


class _Connection:
    def __init__(self, *results: list[dict[str, object]]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, statement: object, params: dict[str, object]) -> _Result:
        self.calls.append((str(statement), params))
        return _Result(self._results.pop(0))


def _prd(status: str = "confirmed") -> dict[str, object]:
    return {
        "id": "17",
        "project_version_id": "23",
        "current_version_id": "31",
        "status": status,
    }


class PrdReviewContextTests(unittest.TestCase):
    def test_resolves_review_only_through_exact_current_prd_relation(self) -> None:
        connection = _Connection(
            [{"id": 41}],
            [
                {
                    "id": 41,
                    "project_version_id": 23,
                    "round_no": 2,
                    "status": "passed",
                    "summary": "ready",
                    "row_version": 4,
                }
            ],
            [
                {
                    "object_id": 17,
                    "object_version_id": 31,
                    "content_hash": "sha256:current",
                }
            ],
        )

        review = _current_review(connection, prd=_prd())

        self.assertEqual("41", review["id"])
        self.assertEqual("31", review["scope"]["prd_version_id"])
        selection_sql, selection_params = connection.calls[0]
        self.assertIn("scope.object_version_id=:version_id", selection_sql)
        self.assertIn("scope.content_hash=version.content_hash", selection_sql)
        self.assertNotIn("ORDER BY", selection_sql.upper())
        self.assertEqual(
            {"project_version_id": 23, "prd_id": 17, "version_id": 31},
            selection_params,
        )

    def test_rejects_ambiguous_current_review_relation(self) -> None:
        connection = _Connection([{"id": 41}, {"id": 42}])

        with self.assertRaises(ApiError) as raised:
            _current_review(connection, prd=_prd())

        self.assertEqual("INVALID_STATE", raised.exception.code)
        self.assertEqual(409, raised.exception.http_status)

    def test_rejects_missing_review_for_confirmed_prd(self) -> None:
        connection = _Connection([])

        with self.assertRaises(ApiError) as raised:
            _current_review(connection, prd=_prd())

        self.assertEqual("INVALID_STATE", raised.exception.code)
        self.assertEqual(409, raised.exception.http_status)

    def test_draft_prd_without_review_remains_valid(self) -> None:
        connection = _Connection([])

        self.assertIsNone(_current_review(connection, prd=_prd("draft")))


if __name__ == "__main__":
    unittest.main()
