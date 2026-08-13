from app.context.base import ContextItem, ContextRequest
from app.context.stub import ContextStub


def item(source_id: str, tokens: int) -> ContextItem:
    return ContextItem(
        source_type="fixture",
        source_id=source_id,
        source_version_id="fixture-v1",
        role="authoritative",
        content_fingerprint="b" * 64,
        content_summary=f"controlled {source_id}",
        token_count=tokens,
    )


def test_only_requested_sources_within_budget_are_injected() -> None:
    provider = ContextStub({"formal": item("formal", 10), "history": item("history", 8)})
    snapshot = provider.get_snapshot(
        ContextRequest(
            task_public_id="task-1",
            project_id="1",
            project_version_id="2",
            requested_source_ids=("formal", "history", "missing"),
            token_budget=12,
        )
    )
    assert [entry.source_id for entry in snapshot.injected] == ["formal"]
    assert snapshot.excluded_source_ids == ("history", "missing")
    assert snapshot.total_tokens == 10
