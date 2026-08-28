import json

import httpx
import pytest

from app.providers.base import (
    MalformedResponseSubtype,
    ProviderAuthenticationFailed,
    ProviderBadRequest,
    ProviderMalformedResponse,
    ProviderRateLimited,
    ProviderRequest,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.openai_compatible import OpenAICompatibleAdapter
from app.providers.profiles import deepseek_profile


def provider_request(model: str = "deepseek-v4-flash") -> ProviderRequest:
    return ProviderRequest(
        trace_id="trace-1",
        task_public_id="task-1",
        model=model,
        prompt_fingerprint="a" * 64,
        input_text="controlled fixture",
    )


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_deepseek_profile_uses_current_models_and_calculates_available_cost() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-only-key"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert body["thinking"] == {"type": "disabled"}
        assert body["temperature"] == 0.2
        assert body["stream"] is False
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            json={
                "id": "provider-request-1",
                "choices": [{"message": {"content": "candidate"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 1000,
                    "prompt_cache_hit_tokens": 100,
                    "prompt_cache_miss_tokens": 900,
                    "completion_tokens": 100,
                    "total_tokens": 1100,
                },
            },
        )

    adapter = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(handler),
    )
    response = adapter.generate(provider_request())
    assert response.provider == "deepseek"
    assert response.usage.estimated_cost == "0.000154"
    assert response.usage.cost_source == "profile_calculated"
    assert response.usage.pricing_version == "2026-07-29"
    assert "test-only-key" not in repr(adapter)


def test_schema_request_uses_responses_api_and_parses_structured_output() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["result_kind"],
        "properties": {"result_kind": {"const": "questions"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/responses"
        body = json.loads(request.content)
        assert body["reasoning"] == {"effort": "none"}
        assert body["text"]["format"] == {
            "type": "json_schema",
            "name": "requirement_candidate",
            "schema": schema,
        }
        assert body["stream"] is False
        assert "store" not in body
        return httpx.Response(
            200,
            json={
                "id": "response-1",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": '{"result_kind":"questions"}'}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "input_tokens_details": {"cached_tokens": 100},
                    "output_tokens": 100,
                    "total_tokens": 1100,
                },
            },
        )

    request = provider_request().model_copy(
        update={
            "response_schema_name": "requirement_candidate",
            "response_schema": schema,
        }
    )
    adapter = OpenAICompatibleAdapter(
        deepseek_profile(), api_key="test-only-key", client=client(handler)
    )
    response = adapter.generate(request)
    assert response.content == '{"result_kind":"questions"}'
    assert response.finish_reason == "stop"
    assert response.usage.input_tokens == 1000
    assert response.usage.output_tokens == 100
    assert response.usage.estimated_cost == "0.000154"


@pytest.mark.parametrize(
    ("reason", "subtype"),
    [
        ("max_output_tokens", MalformedResponseSubtype.TRUNCATED_RESPONSE),
        ("content_filter", MalformedResponseSubtype.FILTERED_RESPONSE),
    ],
)
def test_responses_api_incomplete_status_is_fail_closed(reason, subtype) -> None:
    request = provider_request().model_copy(
        update={"response_schema_name": "candidate", "response_schema": {"type": "object"}}
    )
    adapter = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(
            lambda request: httpx.Response(
                200,
                json={
                    "id": "response-1",
                    "status": "incomplete",
                    "incomplete_details": {"reason": reason},
                    "output": [],
                    "usage": {},
                },
            )
        ),
    )
    with pytest.raises(ProviderMalformedResponse) as caught:
        adapter.generate(request)
    assert caught.value.subtype == subtype


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(401, ProviderAuthenticationFailed), (429, ProviderRateLimited)],
)
def test_adapter_classifies_provider_errors(status_code, error_type) -> None:
    adapter = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(lambda request: httpx.Response(status_code, json={"error": "fixture"})),
    )
    with pytest.raises(error_type):
        adapter.generate(provider_request())


def test_adapter_rejects_model_outside_profile_without_network() -> None:
    adapter = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(lambda request: pytest.fail("network transport must not run")),
    )
    with pytest.raises(ProviderBadRequest, match="model is not allowed"):
        adapter.generate(provider_request("legacy-model"))


def test_live_client_construction_requires_explicit_network_authorization() -> None:
    with pytest.raises(ValueError, match="explicit authorization"):
        OpenAICompatibleAdapter(deepseek_profile(), api_key="test-only-key")


def test_adapter_classifies_timeout_without_exposing_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture timeout", request=request)

    adapter = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(handler),
    )
    with pytest.raises(ProviderTimeout) as caught:
        adapter.generate(provider_request())
    assert "test-only-key" not in str(caught.value)


def test_adapter_classifies_server_and_malformed_responses() -> None:
    unavailable = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(lambda request: httpx.Response(503, json={})),
    )
    with pytest.raises(ProviderUnavailable):
        unavailable.generate(provider_request())

    malformed = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(lambda request: httpx.Response(200, json={"choices": []})),
    )
    with pytest.raises(ProviderMalformedResponse) as malformed_error:
        malformed.generate(provider_request())
    assert malformed_error.value.subtype == MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA

    incomplete = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]})),
    )
    with pytest.raises(ProviderMalformedResponse, match="truncated") as truncated_error:
        incomplete.generate(provider_request())
    assert truncated_error.value.subtype == MalformedResponseSubtype.TRUNCATED_RESPONSE
