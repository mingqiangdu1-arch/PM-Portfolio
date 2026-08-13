from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.providers.base import (
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
    """Minimal Chat Completions adapter with injectable transport for tests."""

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
        try:
            response = self._client.post(
                f"{self._profile.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": request.model,
                    "messages": [{"role": "user", "content": request.input_text}],
                    "stream": False,
                },
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
            content = payload["choices"][0]["message"]["content"]
            finish_reason = payload["choices"][0].get("finish_reason", "stop")
            usage = payload.get("usage", {})
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderMalformedResponse("provider response schema mismatch") from exc
        if finish_reason not in {"stop", "length", "content_filter"}:
            raise ProviderMalformedResponse("unsupported provider finish_reason")

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
