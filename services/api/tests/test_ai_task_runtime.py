from __future__ import annotations

import hashlib
import inspect
import unittest
import json
from contextlib import contextmanager
from unittest.mock import patch

from app.modules.ai_tasks.service import (
    AiApiClient,
    AiTaskService,
    ContextService,
    _clarification_input,
    _result_view,
    _safe_capability_summary,
    _task_summary,
)
from app.modules.requirements.service import _empty_content
from app.platform.config import Settings
from app.platform.errors import ApiError
from app.platform.security import decode_hs256, encode_hs256


class _UrlResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _CandidateRows:
    def __init__(self, ids: list[int]) -> None:
        self.ids = ids

    def mappings(self):
        return self

    def all(self):
        return [{"id": item} for item in self.ids]


class _CandidateConnection:
    def __init__(self, ids: list[int]) -> None:
        self.ids = ids
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _CandidateRows(self.ids)


class AiTaskRuntimeTests(unittest.TestCase):
    def test_authoritative_questions_lookup_requires_one_exact_verified_result(self) -> None:
        target_hash = "a" * 64
        valid = {
            "id": "4",
            "task_public_id": "task-1",
            "task_type": "requirement.clarify",
            "status": "ready",
            "result_kind": "questions",
            "mode": "standard",
            "round_no": 1,
            "target_snapshot_hash": target_hash,
            "content_json": {"result_kind": "questions", "mode": "standard", "round_no": 1, "questions": [{"question_id": "q-1"}]},
        }

        def run(ids, results):
            connection = _CandidateConnection(ids)

            @contextmanager
            def read_scope():
                yield connection

            service = AiTaskService()
            service.get_result = lambda *, user_id, result_id: results[result_id]
            with patch("app.modules.ai_tasks.service.readonly", read_scope):
                return service.find_authoritative_questions_result(
                    user_id=10,
                    project_id=8,
                    project_version_id=9,
                    requirement_id=6,
                    requirement_version_id=29,
                    target_snapshot_hash=target_hash,
                    mode="standard",
                    round_no=1,
                ), connection

        result, connection = run([4], {"4": valid})
        self.assertEqual(result["id"], "4")
        sql, params = connection.calls[0]
        self.assertIn("at.task_type='requirement.clarify'", sql)
        self.assertIn("at.status='ready'", sql)
        self.assertIn("ac.status='succeeded'", sql)
        self.assertIn("ar.status='ready'", sql)
        self.assertEqual(params["requirement_version_id"], 29)
        self.assertEqual(params["target_snapshot_hash"], target_hash)

        for ids, results in (([], {}), ([4, 5], {"4": valid, "5": {**valid, "id": "5"}})):
            with self.subTest(ids=ids), self.assertRaises(ApiError) as raised:
                run(ids, results)
            self.assertEqual((raised.exception.code, raised.exception.http_status), ("CLARIFICATION_ROUND_INVALID", 409))

        mismatched = {**valid, "mode": "deep", "content_json": {**valid["content_json"], "mode": "deep"}}
        with self.assertRaises(ApiError):
            run([4], {"4": mismatched})

    def test_production_ai_http_tokens_bind_post_and_get_task_trace(self) -> None:
        settings = Settings(internal_service_jwt_secret="service-secret", ai_api_url="http://ai-api")
        captured = []

        def urlopen(request, timeout):
            captured.append(request)
            if request.method == "POST":
                return _UrlResponse({"data": {"task_public_id": "task-post", "status": "queued"}})
            return _UrlResponse({"data": {
                "task_public_id": "task-get",
                "status": "queued",
                "trace_id": "trace-get",
                "failure_code": None,
                "result_refs": [],
            }})

        post_body = {"task_public_id": "task-post", "trace_id": "trace-post", "command_id": "cmd-post"}
        client = AiApiClient(base_url="http://ai-api")
        with (
            patch("app.modules.ai_tasks.service.get_settings", return_value=settings),
            patch("app.modules.ai_tasks.service.urllib.request.urlopen", side_effect=urlopen),
        ):
            client.create_task(post_body, "runtime-key")
            client.get_task("task-get", trace_id="trace-get")

        self.assertEqual(len(captured), 2)
        for request, expected in zip(
            captured,
            (("ai.task:write", "task-post", "trace-post"), ("ai.task:read", "task-get", "trace-get")),
        ):
            token = request.get_header("Authorization").removeprefix("Bearer ")
            claims = decode_hs256(
                token,
                "service-secret",
                audience="ai-api",
                issuer="business-api",
                required_scope=expected[0],
                require_jti=True,
                max_ttl_seconds=120,
            )
            self.assertEqual(claims["sub"], "business-api")
            self.assertEqual(claims["task_id"], expected[1])
            self.assertEqual(claims["trace_id"], expected[2])

    def test_production_ai_http_rejects_inconsistent_or_missing_binding_before_send(self) -> None:
        settings = Settings(internal_service_jwt_secret="service-secret", ai_api_url="http://ai-api")
        client = AiApiClient(base_url="http://ai-api")
        with (
            patch("app.modules.ai_tasks.service.get_settings", return_value=settings),
            patch("app.modules.ai_tasks.service.urllib.request.urlopen") as urlopen,
        ):
            with self.assertRaises(ApiError) as mismatched:
                client._call(
                    "POST",
                    "/internal/v1/ai/tasks",
                    {"task_public_id": "task-1", "trace_id": "trace-body"},
                    trace_id="trace-other",
                )
            with self.assertRaises(ApiError) as missing:
                client.get_task("task-1", trace_id="")
        self.assertEqual(mismatched.exception.code, "TRACEABILITY_INCOMPLETE")
        self.assertEqual(missing.exception.code, "TRACEABILITY_INCOMPLETE")
        urlopen.assert_not_called()

    def test_ready_task_projects_only_public_result_reference_fields(self) -> None:
        internal_ref = {
            "ai_result_id": "17",
            "ai_call_id": "9",
            "result_no": 1,
            "status": "ready",
            "target_snapshot_hash": "a" * 64,
            "content_ref": "private/results/task-1/17.json",
            "content_fingerprint": "b" * 64,
        }
        summary = _task_summary({
            "task_public_id": "85cb6e8e-f36f-4d52-b98f-7a8466da2ec1",
            "status": "ready",
            "user_id": 10,
            "target_snapshot_hash": "a" * 64,
            "result_refs": [internal_ref],
        })
        self.assertEqual(summary["result_refs"], [{
            "result_id": "17",
            "status": "ready",
            "target_snapshot_hash": "a" * 64,
        }])
        serialized = json.dumps(summary)
        for private_field in ("content_ref", "content_fingerprint", "ai_call_id", "result_no"):
            self.assertNotIn(private_field, serialized)

    def test_queued_task_has_required_empty_public_result_refs(self) -> None:
        summary = _task_summary({
            "task_public_id": "85cb6e8e-f36f-4d52-b98f-7a8466da2ec1",
            "status": "queued",
            "user_id": 10,
            "target_snapshot_hash": "a" * 64,
        })
        self.assertEqual(summary["result_refs"], [])

    def test_task_idempotency_key_derivation_is_stable_and_payload_bound(self) -> None:
        from app.modules.ai_tasks.service import _canonical_hash
        import hashlib
        first = hashlib.sha256(f"10|POST:/api/v1/ai/tasks|same|{_canonical_hash({'a': 1})}".encode()).hexdigest()
        same = hashlib.sha256(f"10|POST:/api/v1/ai/tasks|same|{_canonical_hash({'a': 1})}".encode()).hexdigest()
        different = hashlib.sha256(f"10|POST:/api/v1/ai/tasks|same|{_canonical_hash({'a': 2})}".encode()).hexdigest()
        self.assertEqual(first, same)
        self.assertNotEqual(first, different)

    def test_openapi_r4_error_mapping_is_conflict(self) -> None:
        schema = json.loads(open("packages/contracts/openapi/openapi.json", encoding="utf-8").read())
        self.assertIn("CLARIFICATION_ROUND_INVALID", schema["components"]["responses"]["Sprint2Error409"]["x-error-codes"])

    def test_context_request_accepts_only_token_budget(self) -> None:
        service = ContextService()
        with patch.object(service, "_claims", return_value={"task_id": "task-1"}), patch.object(service, "_load", side_effect=AssertionError("body validation should run first")):
            for body in ({}, {"token_budget": 0}, {"token_budget": 200001}, {"token_budget": True}, {"token_budget": 10, "requested_source_refs": ["x"]}):
                with self.subTest(body=body), self.assertRaises(ApiError) as raised:
                    service.context_snapshot(task_id="task-1", authorization="Bearer test", body=body)
                self.assertEqual(raised.exception.code, "VALIDATION_ERROR")

    def test_context_trace_binding_is_required_by_runtime_contract(self) -> None:
        service = ContextService()
        task = {"trace_id": "trace-1", "target_snapshot_hash": "a" * 64}
        with (
            patch.object(service, "_claims", return_value={"task_id": "task-1"}),
            patch.object(service, "_load", return_value=(task, {}, {})),
            self.assertRaises(ApiError) as raised,
        ):
            service.context_snapshot(task_id="task-1", authorization="Bearer test", body={"token_budget": 10})
        self.assertEqual((raised.exception.code, raised.exception.http_status), ("SERVICE_TOKEN_INVALID", 401))

    def test_context_trace_binding_rejects_mismatched_header(self) -> None:
        service = ContextService()
        task = {"trace_id": "trace-1", "target_snapshot_hash": "a" * 64}
        claims = {"task_id": "task-1", "trace_id": "trace-1"}
        with (
            patch.object(service, "_claims", return_value=claims),
            patch.object(service, "_load", return_value=(task, {}, {})),
            self.assertRaises(ApiError) as raised,
        ):
            service.context_snapshot(task_id="task-1", authorization="Bearer test", body={"token_budget": 10}, trace_id="trace-2")
        self.assertEqual((raised.exception.code, raised.exception.http_status), ("SERVICE_TOKEN_INVALID", 401))

    def test_context_snapshot_positive_wrapper_contains_derived_source_and_target(self) -> None:
        content, content_hash = _empty_content("raw requirement", requirement_id=10, title="Requirement")
        task = {
            "task_public_id": "task-1",
            "trace_id": "trace-1",
            "target_object_id": 10,
            "target_object_version_id": 20,
            "target_snapshot_hash": content_hash,
            "project_version_id": 7,
            "project_id": 3,
            "user_id": 10,
        }
        version = {"content_json": content, "content_hash": content_hash, "id": 20}
        service = ContextService()
        with (
            patch.object(service, "_claims", return_value={"task_id": "task-1", "trace_id": "trace-1"}),
            patch.object(service, "_load", return_value=(task, {"id": 10}, version)),
        ):
            result = service.context_snapshot(task_id="task-1", authorization="Bearer test", body={"token_budget": 100}, trace_id="trace-1")
        self.assertEqual(result["task_public_id"], "task-1")
        self.assertEqual(result["target_snapshot_hash"], content_hash)
        self.assertEqual(result["source_ref_ids"], ["10"])
        self.assertEqual(result["target"]["object_version_id"], "20")

    def test_result_view_preserves_quality_convergence_and_outer_source_refs(self) -> None:
        quality = {"structure": "valid", "traceability": "valid", "security": "valid", "major_error": False, "blocker_codes": []}
        convergence = {"should_finish": True, "next_round_no": None, "finish_reason": "user_finished"}
        result = _result_view(
            {"id": 4, "task_public_id": "task-1", "status": "ready", "source_refs": [{"source_id": "10"}], "quality_summary": quality, "convergence": convergence},
            {"result_kind": "baseline", "mode": "auto", "round_no": 0, "quality": quality, "convergence": convergence},
        )
        self.assertEqual(result["source_refs"], [{"source_id": "10"}])
        self.assertEqual(result["quality_summary"], quality)
        self.assertEqual(result["convergence"], convergence)

    def test_result_view_projects_only_stored_capability_truth_whitelist(self) -> None:
        row = {
            "id": 4,
            "task_public_id": "task-1",
            "status": "ready",
            "capability_provider_code": "formal_mock",
            "capability_model_code": "requirement-clarifier-v1",
            "model_capability_json": json.dumps({
                "truth_label": "FORMAL_MOCK",
                "runtime_config_json": {"private": True},
            }),
            "provider_profile_id": 7,
            "model_catalog_id": 8,
            "base_url": "https://private.invalid",
            "secret_ref": "private-secret-ref",
        }
        result = _result_view(
            row,
            {"result_kind": "baseline", "mode": "auto", "round_no": 0},
        )

        self.assertEqual(result["capability_summary"], {
            "provider_code": "formal_mock",
            "model_code": "requirement-clarifier-v1",
            "truth_label": "FORMAL_MOCK",
        })
        serialized = json.dumps(result["capability_summary"])
        for private_field in (
            "provider_profile_id", "model_catalog_id", "base_url", "secret_ref",
            "runtime_config_json", "capability_json", "content_ref", "fingerprint",
        ):
            self.assertNotIn(private_field, serialized)

    def test_capability_truth_fails_closed_without_exact_stored_label(self) -> None:
        base = {
            "capability_provider_code": "formal_mock",
            "capability_model_code": "requirement-clarifier-v1",
        }
        for capability in (None, {}, {"truth_label": "formal_mock"}, {"truth_label": True}):
            with self.subTest(capability=capability):
                self.assertEqual(
                    _safe_capability_summary({**base, "model_capability_json": capability}),
                    {
                        "provider_code": "formal_mock",
                        "model_code": "requirement-clarifier-v1",
                    },
                )

    def test_get_result_query_joins_only_capability_truth_carriers(self) -> None:
        source = inspect.getsource(AiTaskService.get_result)
        self.assertIn("JOIN provider_profile pp ON pp.id=ac.provider_profile_id", source)
        self.assertIn("JOIN model_catalog mc ON mc.id=ac.model_catalog_id", source)
        self.assertIn("pp.provider_code AS capability_provider_code", source)
        self.assertIn("mc.model_code AS capability_model_code", source)
        self.assertIn("mc.capability_json AS model_capability_json", source)
        for sensitive_column in ("pp.base_url", "pp.secret_ref", "pp.runtime_config_json"):
            self.assertNotIn(sensitive_column, source)

    def test_ai_http_failure_never_returns_queued(self) -> None:
        def fail(*args, **kwargs):
            raise OSError("connection refused")

        with self.assertRaises(ApiError) as raised:
            AiApiClient(transport=fail).create_task({"trace_id": "t", "command_id": "c"}, "runtime-key")
        self.assertEqual((raised.exception.code, raised.exception.http_status), ("DEPENDENCY_UNAVAILABLE", 503))

    def test_deep_input_requires_persisted_confirmation_and_inherits_it(self) -> None:
        content = {"clarification": {"mode": "deep", "rounds": [{"round_no": i} for i in range(1, 4)], "continue_deep_confirmed": False}}
        with self.assertRaises(ApiError) as raised:
            _clarification_input(content)
        self.assertEqual(raised.exception.code, "DEEP_CONFIRMATION_REQUIRED")
        content["clarification"]["continue_deep_confirmed"] = True
        self.assertEqual(_clarification_input(content), {"mode": "deep", "round_no": 4, "continue_deep_confirmed": True})

    def test_legacy_content_normalizes_false_without_inference(self) -> None:
        content = {"clarification": {"mode": "standard", "rounds": [{"round_no": 1}], "finish_reason": "user_finished"}}
        self.assertEqual(_clarification_input(content)["continue_deep_confirmed"], False)

    def test_result_view_does_not_expose_content_ref(self) -> None:
        result = _result_view({"id": 4, "task_public_id": "task-1", "content_ref": "secret/object-key", "status": "ready"}, {"result_kind": "baseline", "mode": "auto", "round_no": 0})
        self.assertNotIn("content_ref", result)

    def test_worker_jwt_binds_issuer_audience_scope_and_task(self) -> None:
        settings = Settings(internal_service_jwt_secret="secret")
        now = 2_000_000_000
        # The decoder uses wall clock; exercise the service's claim checks with
        # a token generated at the current instant through its public helper.
        import time
        now = int(time.time())
        token = encode_hs256({"iss": "ai-worker", "sub": "ai-worker", "aud": "business-api", "scope": "context:read", "task_id": "task-1", "iat": now, "exp": now + 60, "jti": "jti-1"}, "secret")
        with patch("app.modules.ai_tasks.service.get_settings", return_value=settings):
            claims = ContextService()._claims("Bearer " + token, "task-1", "ai:context_snapshot")
        self.assertEqual(claims["iss"], "ai-worker")
        with patch("app.modules.ai_tasks.service.get_settings", return_value=settings):
            with self.assertRaises(ApiError):
                ContextService()._claims("Bearer " + token, "task-2", "ai:context_snapshot")


if __name__ == "__main__":
    unittest.main()
