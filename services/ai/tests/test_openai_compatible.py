import json

import httpx
import pytest

from app.providers.base import (
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
    with pytest.raises(ProviderMalformedResponse):
        malformed.generate(provider_request())

    incomplete = OpenAICompatibleAdapter(
        deepseek_profile(),
        api_key="test-only-key",
        client=client(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]})),
    )
    with pytest.raises(ProviderMalformedResponse, match="truncated"):
        incomplete.generate(provider_request())
