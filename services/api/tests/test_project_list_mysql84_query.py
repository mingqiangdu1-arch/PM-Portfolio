from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from app.modules.sprint1 import service as sprint1_service


class _ProjectListConnection:
    def __init__(self) -> None:
        self.statement = ""
        self.parameters: dict[str, Any] = {}

    def execute(self, statement: Any, parameters: dict[str, Any]) -> list[tuple[Any, ...]]:
        self.statement = str(statement)
        self.parameters = parameters
        return [
            (29, datetime(2026, 8, 13, 2, 0, tzinfo=UTC)),
            (11, datetime(2026, 8, 12, 2, 0, tzinfo=UTC)),
        ]


def test_list_projects_distinct_projection_supports_mysql84_ordering(monkeypatch: Any) -> None:
    connection = _ProjectListConnection()

    @contextmanager
    def fake_readonly() -> Iterator[_ProjectListConnection]:
        yield connection

    summarized_ids: list[int] = []

    def fake_project_summary(_connection: Any, project_id: int, user_id: int) -> dict[str, Any]:
        assert _connection is connection
        assert user_id == 7
        summarized_ids.append(project_id)
        return {"id": str(project_id)}

    monkeypatch.setattr(sprint1_service, "readonly", fake_readonly)
    monkeypatch.setattr(sprint1_service, "_project_summary", fake_project_summary)

    result = sprint1_service.Sprint1Service.__new__(sprint1_service.Sprint1Service).list_projects(
        user_id=7,
        limit=2,
    )

    normalized_sql = " ".join(connection.statement.split())
    assert "SELECT DISTINCT p.id,p.updated_at FROM project p" in normalized_sql
    assert "ORDER BY p.updated_at DESC,p.id DESC LIMIT" in normalized_sql
    assert connection.parameters == {"uid": 7, "limit": 2}
    assert summarized_ids == [29, 11]
    assert result == {
        "items": [{"id": "29"}, {"id": "11"}],
        "next_cursor": None,
        "has_more": False,
    }
