import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
import json
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from datetime import UTC, datetime
from fastapi.testclient import TestClient

from app.context.runtime import P1RuntimeContextResponse
from app.context.runtime import BusinessContextClient
import httpx
from app.integrations.result_storage import ObjectWriteError, S3ResultObjectStore, build_result_key, canonical_json
from app.requirement_clarification.bundle import BundleResolutionError, resolve_formal_mock
from app.tasking.repository import IdempotencyConflict, InMemoryTaskRepository, TaskRecord
from app.api.tasks import Input, configure_task_dependencies
from app.main import create_app
from app.security import ServiceJwtIssuer
from app.tasking.repository import MySQLTaskRepository


def context_payload(*, raw="hello", saved=False):
    return {
        "contract_version": "p1-runtime-context.v1", "task_public_id": "t1",
        "target": {"object_type": "requirement", "object_id": "1", "object_version_id": "2"},
        "target_snapshot_hash": "a" * 64,
        "input": {"mode": "deep", "round_no": 4, "continue_deep_confirmed": saved},
        "source_ref_ids": ["9"], "risk_acceptances": [],
        "requirement_content": {"raw_input": raw, "raw_input_ref": {"source_id": "9", "content_hash": hashlib.sha256(raw.encode()).hexdigest()}, "clarification": {"mode": "deep", "continue_deep_confirmed": saved}, "baseline": {}}
    }


def test_context_requires_saved_confirmation_and_raw_hash():
    with pytest.raises(ValueError): P1RuntimeContextResponse.model_validate(context_payload())
    valid = context_payload(saved=True)
    assert P1RuntimeContextResponse.model_validate(valid).input.continue_deep_confirmed is True
    valid["requirement_content"]["raw_input_ref"]["content_hash"] = "b" * 64
    with pytest.raises(ValueError): P1RuntimeContextResponse.model_validate(valid)

def test_context_request_only_token_budget():
    seen = {}
    def handler(request):
        import json
        seen.update(json.loads(request.content)); return httpx.Response(200, json={"ok": True})
    client = BusinessContextClient(base_url="http://business", token="t", transport=httpx.MockTransport(handler))
    assert client.context_snapshot("t1", trace_id="tr", token_budget=100)["ok"] is True
    assert seen == {"token_budget": 100}


def test_repository_idempotency_and_conflict():
    repo = InMemoryTaskRepository(); task = TaskRecord("t", "1", "2", "3", "4", "5", "a" * 64, "c", "tr")
    assert repo.create_task(task) == repo.create_task(task)
    with pytest.raises(IdempotencyConflict): repo.create_task(TaskRecord("t", "9", "2", "3", "4", "5", "a" * 64, "c", "tr"))


def test_bundle_requires_exactly_one_current_formal_mock():
    row = {"provider_code":"formal_mock", "model_code":"requirement-clarifier-v1", "profile_name":"portfolio-p1-formal-mock", "skill_name":"requirement.clarify", "prompt_name":"requirement.clarify.formal_mock", "template_name":"requirement.clarify.result.0.2", "context_strategy_name":"requirement.clarify.raw-input-only", "version_no":"0.2.0", "active":True, "current":True, "content_hash":"a"*64, "provider_id":1, "model_id":2, "profile_id":3, "skill_version_id":4, "prompt_version_id":5, "template_version_id":6, "context_strategy_version_id":7}
    assert resolve_formal_mock([row]).provider_id == 1
    with pytest.raises(BundleResolutionError): resolve_formal_mock([row, row])


def test_s3_write_once_and_mismatch():
    class Fake:
        def __init__(self): self.objects = {}
        def head_object(self, **kw):
            if kw["Key"] not in self.objects: raise FileNotFoundError
            return {"Metadata": {"sha256": self.objects[kw["Key"]][1]}}
        def put_object(self, **kw): self.objects[kw["Key"]] = (kw["Body"], kw["Metadata"]["sha256"])
    fake = Fake(); store = S3ResultObjectStore(fake, bucket="b")
    key, digest = store.put_result(project_id="1", task_public_id="t", ai_call_id="2", result_no=1, content={"x": 1})
    assert key == build_result_key(prefix="ai-results/", project_id="1", task_public_id="t", ai_call_id="2", result_no=1, content_fingerprint=digest)
    fake.objects[key] = (fake.objects[key][0], "c" * 64)
    with pytest.raises(ObjectWriteError): store.put_result(project_id="1", task_public_id="t", ai_call_id="2", result_no=1, content={"x": 1})


def test_deep_round_validation_matches_frozen_task_envelope():
    with pytest.raises(ValidationError):
        Input(mode="deep", round_no=0, continue_deep_confirmed=False)
    assert Input(mode="deep", round_no=1, continue_deep_confirmed=False).round_no == 1
    with pytest.raises(ValidationError):
        Input(mode="deep", round_no=4, continue_deep_confirmed=False)
    assert Input(mode="deep", round_no=4, continue_deep_confirmed=True).continue_deep_confirmed is True


def test_task_api_idempotency_and_id_only_queue(monkeypatch):
    monkeypatch.setenv("AI_INTERNAL_JWT_SECRET", "test-only-service-secret-with-sufficient-entropy")
    app = create_app()
    class Queue:
        def __init__(self): self.messages = []
        def ensure_available(self): pass
        def enqueue(self, task_public_id, trace_id): self.messages.append((task_public_id, trace_id))
    queue = Queue(); configure_task_dependencies(repository=InMemoryTaskRepository(), queue=queue)
    token = ServiceJwtIssuer(secret="test-only-service-secret-with-sufficient-entropy", issuer="business-api", subject="business-api", audience="ai-api").issue(scopes={"ai.task:write", "ai.task:read"}, task_id="t-api", trace_id="tr")
    payload = {"schema_version":"0.2.0", "task_public_id":"t-api", "user_id":"1", "project_id":"2", "project_version_id":"3", "module":"product_design", "task_type":"requirement.clarify", "target":{"object_type":"requirement","object_id":"4","object_version_id":"5"}, "target_snapshot_hash":"a"*64, "source_ref_ids":["9"], "capability_selection":None, "risk_acceptances":[], "command_id":"c", "trace_id":"tr", "requested_at":datetime.now(UTC).isoformat(), "input":{"mode":"auto","round_no":0,"continue_deep_confirmed":False}, "status":"queued"}
    with TestClient(app) as client:
        deep_zero = {**payload, "input":{"mode":"deep","round_no":0,"continue_deep_confirmed":False}}
        rejected = client.post('/internal/v1/ai/tasks', json=deep_zero, headers={'Authorization': f'Bearer {token}'})
        first = client.post('/internal/v1/ai/tasks', json=payload, headers={'Authorization': f'Bearer {token}'})
        second = client.post('/internal/v1/ai/tasks', json=payload, headers={'Authorization': f'Bearer {token}'})
    assert rejected.status_code == 422
    assert first.status_code == second.status_code == 202
    assert queue.messages == [('t-api', 'tr')]


def test_internal_task_get_returns_only_task_scoped_durable_result_refs(monkeypatch):
    monkeypatch.setenv("AI_INTERNAL_JWT_SECRET", "test-only-service-secret-with-sufficient-entropy")
    app = create_app(); repo = InMemoryTaskRepository()
    target = repo.create_task(TaskRecord("t-api", "1", "2", "3", "4", "5", "a" * 64, "c", "tr", db_id=9))
    other = repo.create_task(TaskRecord("t-other", "1", "2", "3", "6", "7", "c" * 64, "other-c", "other-tr", db_id=10))
    configure_task_dependencies(repository=repo, queue=SimpleNamespace())
    issuer = ServiceJwtIssuer(secret="test-only-service-secret-with-sufficient-entropy", issuer="business-api", subject="business-api", audience="ai-api")
    token = issuer.issue(scopes={"ai.task:read"}, task_id="t-api", trace_id="tr")
    with TestClient(app) as client:
        queued = client.get("/internal/v1/ai/tasks/t-api", headers={"Authorization": f"Bearer {token}"})
        assert queued.status_code == 200 and queued.json()["result_refs"] == []
        for status in ("preparing", "generating", "checking", "ready"): repo.update_status("t-api", status)
        repo.record_result({"task_public_id":"t-api", "ai_call_id":2, "result_no":1, "status":"ready", "target_snapshot_hash":"a"*64, "content_ref":"opaque://target", "content_fingerprint":"b"*64})
        repo.record_result({"task_public_id":"t-other", "ai_call_id":3, "result_no":1, "status":"ready", "target_snapshot_hash":"c"*64, "content_ref":"opaque://other", "content_fingerprint":"d"*64})
        ready = client.get("/internal/v1/ai/tasks/t-api", headers={"Authorization": f"Bearer {token}"})
        wrong_token = issuer.issue(scopes={"ai.task:read"}, task_id="t-other", trace_id="other-tr")
        forbidden = client.get("/internal/v1/ai/tasks/t-api", headers={"Authorization": f"Bearer {wrong_token}"})
    assert ready.status_code == 200
    assert ready.json()["result_refs"] == [{"ai_result_id":"1", "ai_call_id":"2", "result_no":1, "status":"ready", "target_snapshot_hash":"a"*64, "content_ref":"opaque://target", "content_fingerprint":"b"*64}]
    assert "opaque://other" not in ready.text and forbidden.status_code == 403 and "opaque://target" not in forbidden.text
    assert repo.tasks["t-api"] == replace(target, status="ready") and repo.tasks["t-other"] == other


def test_mysql_result_refs_query_binds_result_call_and_task():
    class Cursor:
        def execute(self, sql, params=()): self.sql, self.params = sql, params
        def fetchall(self): return [{"ai_result_id":3, "ai_call_id":2, "result_no":1, "status":"ready", "target_snapshot_hash":"a"*64, "content_ref":"opaque://result", "content_fingerprint":"b"*64}]
        def close(self): pass
    class Connection:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def close(self): pass
    connection = Connection(); refs = MySQLTaskRepository(lambda: connection).list_result_refs("t-api")
    assert connection.cursor_value.params == ("t-api",)
    assert "FROM ai_result" in connection.cursor_value.sql and "JOIN ai_call" in connection.cursor_value.sql and "JOIN ai_task" in connection.cursor_value.sql
    assert refs == [{"ai_result_id":"3", "ai_call_id":"2", "result_no":1, "status":"ready", "target_snapshot_hash":"a"*64, "content_ref":"opaque://result", "content_fingerprint":"b"*64}]


def test_ai_outbox_event_envelope_is_complete_and_non_sensitive():
    schema_root = __import__("pathlib").Path(__file__).parents[1] / "schemas" / "v0.1"
    schema = json.loads((schema_root / "ai-outbox-event.schema.json").read_text(encoding="utf-8"))
    envelope_schema = json.loads((schema_root / "event-envelope.schema.json").read_text(encoding="utf-8"))
    schema["allOf"][0] = envelope_schema
    schema["$defs"] = envelope_schema["$defs"]
    def localize(value):
        if isinstance(value, dict): return {key: localize(item) for key, item in value.items()}
        if isinstance(value, list): return [localize(item) for item in value]
        if isinstance(value, str) and value.startswith("event-envelope.schema.json#/"): return value.removeprefix("event-envelope.schema.json")
        return value
    schema = localize(schema)

    class Cursor:
        def execute(self, *args):
            self.args = args

    cursor = Cursor()
    task = TaskRecord("t", "1", "2", "3", "4", "5", "a" * 64, "command", "trace", db_id=9)
    MySQLTaskRepository._insert_outbox(cursor, task, event_name="ai.result.generated", result_status="success", now=datetime.now(UTC), ai_call_id=2, ai_result_id=3, result_payload={"candidate_only": True, "result_id": "3", "content_fingerprint": "b" * 64, "target_snapshot_hash": "a" * 64})
    envelope = json.loads(cursor.args[1][6])
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(envelope)
    assert envelope["schema_version"] == "0.1.3"
    assert "content_ref" not in json.dumps(envelope)
    assert "secret" not in json.dumps(envelope).lower()


def test_canonical_json_is_utf8_sorted_and_has_no_trailing_whitespace():
    assert canonical_json({"z": "中文", "a": {"b": 2, "a": 1}}) == '{"a":{"a":1,"b":2},"z":"中文"}'.encode("utf-8")
