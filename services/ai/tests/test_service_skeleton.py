from app.api.health import readiness_payload
from app.core.config import Settings
from app.integrations import DependencyHealth
from app.workers.celery_app import celery_app


def test_health_exposes_stage_state_without_fake_progress(monkeypatch) -> None:
    monkeypatch.delenv("FLOW_ENABLED", raising=False)
    payload = readiness_payload(Settings.from_env(), broker_available=True)
    assert payload["status"] == "ready"
    assert payload["dependencies"]["broker"] == "available"
    assert payload["accepting_new_tasks"] is True
    assert payload["flow_enabled"] is False
    assert "progress" not in payload


def test_readiness_rejects_new_tasks_when_redis_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("AI_ENVIRONMENT", raising=False)
    payload = readiness_payload(Settings.from_env(), broker_available=False)
    assert payload["status"] == "dependency_unavailable"
    assert payload["accepting_new_tasks"] is False


def test_health_keeps_ai_capability_separate_from_business_crud(monkeypatch) -> None:
    monkeypatch.delenv("FLOW_ENABLED", raising=False)
    payload = readiness_payload(
        Settings.from_env(),
        broker_available=False,
        business_api=DependencyHealth("available"),
    )
    assert payload["capabilities"] == {"ai_tasks": "unavailable"}
    assert "project_crud" not in payload["capabilities"]
    assert payload["dependencies"]["business_api"] == "available"


def test_worker_does_not_use_redis_as_result_source_of_truth() -> None:
    assert celery_app.conf.result_backend is None
    assert celery_app.conf.task_ignore_result is True
