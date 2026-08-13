from __future__ import annotations

from app.context.base import ContextItem, ContextRequest, ContextSnapshot


class ContextStub:
    """Returns only explicitly requested, pre-authorized fixture sources."""

    def __init__(self, fixtures: dict[str, ContextItem]) -> None:
        self._fixtures = dict(fixtures)

    def get_snapshot(self, request: ContextRequest) -> ContextSnapshot:
        injected: list[ContextItem] = []
        excluded: list[str] = []
        remaining = request.token_budget
        for source_id in request.requested_source_ids:
            item = self._fixtures.get(source_id)
            if item is None or item.token_count > remaining:
                excluded.append(source_id)
                continue
            injected.append(item)
            remaining -= item.token_count
        return ContextSnapshot(
            task_public_id=request.task_public_id,
            injected=tuple(injected),
            excluded_source_ids=tuple(excluded),
            total_tokens=sum(item.token_count for item in injected),
        )
