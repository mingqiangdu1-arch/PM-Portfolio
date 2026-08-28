from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.providers.base import (
    MalformedResponseSubtype,
    ProviderAuthenticationFailed,
    ProviderBadRequest,
    ProviderMalformedResponse,
    ProviderRateLimited,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUsage,
)


@dataclass(frozen=True, slots=True)
class ModelPrice:
    cached_input_per_million: Decimal
    uncached_input_per_million: Decimal
    output_per_million: Decimal


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProfile:
    profile_id: str
    base_url: str
    allowed_models: tuple[str, ...]
    timeout_seconds: float
    pricing_version: str | None
    prices: dict[str, ModelPrice]


class OpenAICompatibleAdapter:
    """Minimal OpenAI-compatible adapter with injectable transport for tests."""

    def __init__(
        self,
        profile: OpenAICompatibleProfile,
        *,
        api_key: str,
        client: httpx.Client | None = None,
        network_authorized: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError("provider API key is required")
        if client is None and not network_authorized:
            raise ValueError("live provider network call requires explicit authorization")
        self._profile = profile
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=profile.timeout_seconds)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if request.model not in self._profile.allowed_models:
            raise ProviderBadRequest("model is not allowed by provider profile")
        if (request.response_schema is None) != (request.response_schema_name is None):
            raise ProviderBadRequest("response schema name and schema must be provided together")
        use_responses_api = request.response_schema is not None
        if use_responses_api:
            url = f"{self._profile.base_url.rstrip('/')}/responses"
            body = {
                "model": request.model,
                "instructions": (
                    "Return exactly one JSON object matching the supplied JSON Schema. "
                    "Do not use markdown or prose outside JSON."
                ),
                "input": request.input_text,
                "reasoning": {"effort": "none"},
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": request.response_schema_name,
                        "schema": request.response_schema,
                    }
                },
                "max_output_tokens": 4096,
                "temperature": 0.2,
                "stream": False,
            }
        else:
            url = f"{self._profile.base_url.rstrip('/')}/chat/completions"
            body = {
                "model": request.model,
                "thinking": {"type": "disabled"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return exactly one valid JSON object. Do not use markdown or prose outside JSON.",
                    },
                    {"role": "user", "content": request.input_text},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 4096,
                "temperature": 0.2,
                "stream": False,
            }
        try:
            response = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("provider request timed out") from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable("provider transport unavailable") from exc

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationFailed("provider authentication failed")
        if response.status_code == 429:
            raise ProviderRateLimited("provider rate limited")
        if response.status_code >= 500:
            raise ProviderUnavailable("provider server unavailable")
        if response.status_code >= 400:
            raise ProviderBadRequest("provider rejected request")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderMalformedResponse(
                "provider response schema mismatch",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
            ) from exc
        if use_responses_api:
            content, finish_reason, usage = self._parse_responses_payload(payload)
        else:
            content, finish_reason, usage = self._parse_chat_completions_payload(payload)
        if finish_reason not in {"stop", "length", "content_filter"}:
            raise ProviderMalformedResponse(
                "unsupported provider finish_reason",
                subtype=MalformedResponseSubtype.UNSUPPORTED_FINISH_REASON,
                field="finish_reason",
            )
        if finish_reason == "length":
            raise ProviderMalformedResponse(
                "provider structured output was truncated",
                subtype=MalformedResponseSubtype.TRUNCATED_RESPONSE,
                field="finish_reason",
            )
        if finish_reason == "content_filter":
            raise ProviderMalformedResponse(
                "provider structured output was filtered",
                subtype=MalformedResponseSubtype.FILTERED_RESPONSE,
                field="finish_reason",
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderMalformedResponse(
                "provider returned empty structured output",
                subtype=MalformedResponseSubtype.EMPTY_CONTENT,
                field="content",
            )

        estimated_cost = self._estimate_cost(request.model, usage)
        return ProviderResponse(
            provider=self._profile.profile_id,
            model=request.model,
            provider_request_id=str(payload.get("id", "unavailable")),
            content=str(content),
            finish_reason=finish_reason,
            usage=ProviderUsage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                billed_tokens=usage.get("total_tokens"),
                estimated_cost=estimated_cost,
                currency_code="USD" if estimated_cost is not None else None,
                cost_source="profile_calculated" if estimated_cost is not None else "unavailable",
                pricing_version=self._profile.pricing_version,
            ),
        )

    @staticmethod
    def _parse_chat_completions_payload(
        payload: Any,
    ) -> tuple[str, str, dict[str, Any]]:
        try:
            content = payload["choices"][0]["message"]["content"]
            finish_reason = payload["choices"][0].get("finish_reason", "stop")
            usage = payload.get("usage", {})
            if not isinstance(usage, dict):
                raise TypeError
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderMalformedResponse(
                "provider response schema mismatch",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
            ) from exc
        return content, finish_reason, usage

    @staticmethod
    def _parse_responses_payload(
        payload: Any,
    ) -> tuple[str, str, dict[str, Any]]:
        try:
            status = payload["status"]
            output = payload["output"]
            raw_usage = payload.get("usage", {})
            if not isinstance(output, list) or not isinstance(raw_usage, dict):
                raise TypeError
        except (KeyError, TypeError) as exc:
            raise ProviderMalformedResponse(
                "provider response schema mismatch",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
            ) from exc
        if status == "incomplete":
            details = payload.get("incomplete_details")
            reason = details.get("reason") if isinstance(details, dict) else None
            if reason == "max_output_tokens":
                raise ProviderMalformedResponse(
                    "provider structured output was truncated",
                    subtype=MalformedResponseSubtype.TRUNCATED_RESPONSE,
                    field="incomplete_details.reason",
                )
            if reason == "content_filter":
                raise ProviderMalformedResponse(
                    "provider structured output was filtered",
                    subtype=MalformedResponseSubtype.FILTERED_RESPONSE,
                    field="incomplete_details.reason",
                )
            raise ProviderMalformedResponse(
                "provider returned an incomplete response",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
                field="status",
            )
        if status == "failed":
            raise ProviderUnavailable("provider response failed")
        if status != "completed":
            raise ProviderMalformedResponse(
                "provider response status is unsupported",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
                field="status",
            )
        messages = [item for item in output if isinstance(item, dict) and item.get("type") == "message"]
        if len(messages) != 1 or messages[0].get("status") != "completed":
            raise ProviderMalformedResponse(
                "provider response message schema mismatch",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
                field="output",
            )
        parts = messages[0].get("content")
        if not isinstance(parts, list):
            raise ProviderMalformedResponse(
                "provider response content schema mismatch",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
                field="output.content",
            )
        output_texts = [
            part.get("text")
            for part in parts
            if isinstance(part, dict) and part.get("type") == "output_text"
        ]
        if len(output_texts) != 1:
            raise ProviderMalformedResponse(
                "provider structured output must contain exactly one text part",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
                field="output.content",
                rule="exactly_one_output_text",
            )
        try:
            input_tokens = int(raw_usage.get("input_tokens", 0))
            output_tokens = int(raw_usage.get("output_tokens", 0))
            total_tokens = int(raw_usage.get("total_tokens", input_tokens + output_tokens))
            input_details = raw_usage.get("input_tokens_details", {})
            if not isinstance(input_details, dict):
                raise TypeError
            cached_tokens = int(input_details.get("cached_tokens", 0))
        except (TypeError, ValueError) as exc:
            raise ProviderMalformedResponse(
                "provider usage schema mismatch",
                subtype=MalformedResponseSubtype.PROVIDER_RESPONSE_SCHEMA,
                field="usage",
            ) from exc
        usage = {
            "prompt_tokens": input_tokens,
            "prompt_cache_hit_tokens": cached_tokens,
            "prompt_cache_miss_tokens": max(0, input_tokens - cached_tokens),
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        return output_texts[0], "stop", usage

    def _estimate_cost(self, model: str, usage: dict[str, Any]) -> str | None:
        price = self._profile.prices.get(model)
        if price is None:
            return None
        cached_tokens = max(0, int(usage.get("prompt_cache_hit_tokens", 0)))
        prompt_tokens = max(cached_tokens, int(usage.get("prompt_tokens", 0)))
        uncached_tokens = max(
            0,
            int(usage.get("prompt_cache_miss_tokens", prompt_tokens - cached_tokens)),
        )
        cached = Decimal(cached_tokens)
        uncached = Decimal(uncached_tokens)
        output = Decimal(max(0, int(usage.get("completion_tokens", 0))))
        cost = (
            cached * price.cached_input_per_million
            + uncached * price.uncached_input_per_million
            + output * price.output_per_million
        ) / Decimal(1_000_000)
        return format(cost.quantize(Decimal("0.000001")), "f")
