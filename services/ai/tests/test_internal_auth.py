import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations import BusinessApiHealthClient
from app.integrations import DependencyHealth
from app.context.runtime import BusinessContextClient
from app.main import create_app
from app.security import ServiceJwtError, ServiceJwtIssuer, ServiceJwtVerifier


SECRET = "test-only-service-secret-with-sufficient-entropy"
NOW = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)


def issuer(*, audience: str = "ai-api", name: str = "business-api", ttl: int = 120) -> ServiceJwtIssuer:
    return ServiceJwtIssuer(secret=SECRET, issuer=name, subject=name, audience=audience, ttl_seconds=ttl)


def verifier() -> ServiceJwtVerifier:
    return ServiceJwtVerifier(secret=SECRET, audience="ai-api", allowed_issuers={"business-api", "monitoring"})


def test_service_jwt_accepts_expected_identity_audience_scope_and_trace() -> None:
    token = issuer().issue(scopes={"health", "ai.task:read"}, trace_id="trace-101", now=NOW, jwt_id="jti-101")
    principal = verifier().verify(token, required_scopes={"health"}, now=NOW)
    assert principal.issuer == "business-api"
    assert principal.trace_id == "trace-101"
    assert principal.jwt_id == "jti-101"


@pytest.mark.parametrize(
    ("token_factory", "code", "status_code"),
    [
        (lambda: issuer(audience="business-api").issue(scopes={"health"}, now=NOW), "SERVICE_TOKEN_AUDIENCE_INVALID", 401),
        (lambda: issuer(name="unknown-service").issue(scopes={"health"}, now=NOW), "SERVICE_TOKEN_ISSUER_INVALID", 401),
        (lambda: issuer().issue(scopes={"ai.task:read"}, now=NOW), "SERVICE_SCOPE_FORBIDDEN", 403),
        (lambda: issuer().issue(scopes={"health"}, now=NOW - timedelta(minutes=10)), "SERVICE_TOKEN_EXPIRED", 401),
    ],
)
def test_service_jwt_rejects_wrong_expired_and_unauthorized_tokens(token_factory, code, status_code) -> None:
    with pytest.raises(ServiceJwtError) as error:
        verifier().verify(token_factory(), required_scopes={"health"}, now=NOW)
    assert error.value.code == code
    assert error.value.status_code == status_code


def test_service_jwt_rejects_task_scope_escalation() -> None:
    token = issuer(audience="business-api", name="ai-worker").issue(scopes={"context:read"}, task_id="task-1", now=NOW)
    worker_verifier = ServiceJwtVerifier(secret=SECRET, audience="business-api", allowed_issuers={"ai-worker"})
    with pytest.raises(ServiceJwtError, match="SERVICE_TASK_SCOPE_FORBIDDEN"):
        worker_verifier.verify(token, required_scopes={"context:read"}, task_id="task-2", now=NOW)


def test_worker_context_token_paths_use_exact_frozen_scope_and_binding() -> None:
    root = Path(__file__).parents[1]
    for relative_path in ("app/workers/tasks.py", "app/main.py"):
        tree = ast.parse((root / relative_path).read_text(encoding="utf-8"))
        issuer_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ServiceJwtIssuer"
        ]
        assert len(issuer_calls) == 1
        issuer_keywords = {keyword.arg: keyword.value for keyword in issuer_calls[0].keywords}
        assert isinstance(issuer_keywords["issuer"], ast.Constant) and issuer_keywords["issuer"].value == "ai-worker"
        assert isinstance(issuer_keywords["subject"], ast.Constant) and issuer_keywords["subject"].value == "ai-worker"
        assert isinstance(issuer_keywords["audience"], ast.Constant) and issuer_keywords["audience"].value == "business-api"
        assert isinstance(issuer_keywords["ttl_seconds"], ast.Attribute) and issuer_keywords["ttl_seconds"].attr == "service_jwt_ttl_seconds"
        issue_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "issue"
        ]
        assert len(issue_calls) == 1
        keywords = {keyword.arg: keyword.value for keyword in issue_calls[0].keywords}
        assert isinstance(keywords["scopes"], ast.Set)
        assert [item.value for item in keywords["scopes"].elts] == ["context:read"]
        assert isinstance(keywords["task_id"], ast.Name) and keywords["task_id"].id == "task_id"
        assert isinstance(keywords["trace_id"], ast.Name) and keywords["trace_id"].id == "trace"


def test_worker_context_requests_preserve_service_identity_task_and_trace_binding() -> None:
    worker_issuer = issuer(audience="business-api", name="ai-worker")
    worker_verifier = ServiceJwtVerifier(
        secret=SECRET,
        audience="business-api",
        allowed_issuers={"ai-worker"},
    )
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"].removeprefix("Bearer ")
        task_id = request.headers["x-task-public-id"]
        principal = worker_verifier.verify(
            token,
            required_scopes={"context:read"},
            task_id=task_id,
        )
        if principal.trace_id != request.headers["x-trace-id"]:
            return httpx.Response(403, json={"detail": "TRACE_BINDING_FORBIDDEN"})
        assert principal.issuer == "ai-worker"
        assert principal.subject == "ai-worker"
        assert principal.audience == "business-api"
        assert principal.scopes == frozenset({"context:read"})
        assert principal.task_id == "task-context-1"
        assert principal.trace_id == "trace-context-1"
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"accepted": True})

    client = BusinessContextClient(
        base_url="http://business-api:8000",
        token=lambda task_id, trace_id: worker_issuer.issue(
            scopes={"context:read"},
            task_id=task_id,
            trace_id=trace_id,
        ),
        transport=httpx.MockTransport(handler),
    )
    assert client.context_snapshot("task-context-1", trace_id="trace-context-1", token_budget=100)["accepted"]
    assert client.target_freshness(
        "task-context-1",
        trace_id="trace-context-1",
        target_snapshot_hash="a" * 64,
    )["accepted"]
    assert seen_paths == [
        "/internal/v1/ai/tasks/task-context-1/context-snapshot",
        "/internal/v1/ai/tasks/task-context-1/target-freshness",
    ]

    cross_task_token = worker_issuer.issue(
        scopes={"context:read"},
        task_id="task-context-1",
        trace_id="trace-context-1",
        now=NOW,
    )
    with pytest.raises(ServiceJwtError, match="SERVICE_TASK_SCOPE_FORBIDDEN"):
        worker_verifier.verify(
            cross_task_token,
            required_scopes={"context:read"},
            task_id="task-context-2",
            now=NOW,
        )

    mismatched_trace_client = BusinessContextClient(
        base_url="http://business-api:8000",
        token=lambda task_id, trace_id: worker_issuer.issue(
            scopes={"context:read"},
            task_id=task_id,
            trace_id="different-trace",
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="business_context_http_403"):
        mismatched_trace_client.context_snapshot(
            "task-context-1",
            trace_id="trace-context-1",
            token_budget=100,
        )


def test_service_jwt_rejects_invalid_signature() -> None:
    token = issuer().issue(scopes={"health"}, now=NOW)
    signing_input, signature = token.rsplit(".", 1)
    tampered_first = "A" if signature[0] != "A" else "B"
    tampered = f"{signing_input}.{tampered_first}{signature[1:]}"
    with pytest.raises(ServiceJwtError, match="SERVICE_TOKEN_SIGNATURE_INVALID"):
        verifier().verify(tampered, required_scopes={"health"}, now=NOW)


def test_internal_health_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("AI_INTERNAL_JWT_SECRET", SECRET)
    response = TestClient(create_app()).get("/internal/v1/ai/health/ready")
    assert response.status_code == 401
    assert response.json()["detail"] == "SERVICE_TOKEN_REQUIRED"


def test_internal_health_rejects_wrong_scope(monkeypatch) -> None:
    monkeypatch.setenv("AI_INTERNAL_JWT_SECRET", SECRET)
    token = issuer().issue(scopes={"ai.task:read"})
    response = TestClient(create_app()).get("/internal/v1/ai/health/ready", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "SERVICE_SCOPE_FORBIDDEN"


def test_business_api_can_call_ai_health_with_frozen_service_contract(monkeypatch) -> None:
    monkeypatch.setenv("AI_INTERNAL_JWT_SECRET", SECRET)
    monkeypatch.setattr("app.api.health.probe_broker", lambda broker_url: True)
    monkeypatch.setattr(
        "app.api.health.probe_business_api",
        lambda settings, trace_id: DependencyHealth("not_required"),
    )
    token = issuer(name="business-api", audience="ai-api").issue(
        scopes={"health"}, trace_id="trace-health-inbound"
    )
    response = TestClient(create_app()).get(
        "/internal/v1/ai/health/ready",
        headers={"Authorization": f"Bearer {token}", "X-Trace-ID": "trace-health-inbound"},
    )
    assert response.status_code == 200
    assert response.json()["capabilities"] == {"ai_tasks": "ready"}
    assert response.json()["flow_enabled"] is False


def test_business_api_probe_uses_service_token_without_reading_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/health"
        token = request.headers["authorization"].removeprefix("Bearer ")
        principal = ServiceJwtVerifier(
            secret=SECRET,
            audience="business-api",
            allowed_issuers={"ai-api"},
        ).verify(token, required_scopes={"health"})
        assert principal.subject == "ai-api"
        assert request.headers["x-trace-id"] == "trace-health-101"
        return httpx.Response(200, json={"sensitive": "body is deliberately ignored"})

    client = BusinessApiHealthClient(
        base_url="http://business-api:8000",
        token_issuer=issuer(audience="business-api", name="ai-api"),
        transport=httpx.MockTransport(handler),
    )
    result = client.probe(trace_id="trace-health-101")
    assert result.available
    assert result.error_class is None


def test_business_api_probe_classifies_auth_failure_without_leaking_body() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(403, text="secret response body"))
    client = BusinessApiHealthClient(
        base_url="http://business-api:8000",
        token_issuer=issuer(audience="business-api", name="ai-api"),
        transport=transport,
    )
    result = client.probe(trace_id="trace-health-102")
    assert result.status == "unavailable"
    assert result.error_class == "authentication"
    assert not hasattr(result, "response_body")
