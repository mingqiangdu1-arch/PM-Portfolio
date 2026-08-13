from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    trace_id: str = Field(min_length=1, max_length=64)
    task_public_id: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    prompt_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_text: str = Field(min_length=1, max_length=100_000)


class ProviderUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    billed_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: str | None = None
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    cost_source: Literal["provider_reported", "profile_calculated", "unavailable"]
    pricing_version: str | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str
    model: str
    provider_request_id: str
    content: str
    finish_reason: Literal["stop", "length", "content_filter"]
    usage: ProviderUsage


class ProviderError(RuntimeError):
    error_class = "provider_error"
    retryable = False


class ProviderRateLimited(ProviderError):
    error_class = "rate_limited"
    retryable = True


class ProviderTimeout(ProviderError):
    error_class = "timeout"
    retryable = True


class ProviderUnavailable(ProviderError):
    error_class = "unavailable"
    retryable = True


class ProviderAuthenticationFailed(ProviderError):
    error_class = "authentication_failed"
    retryable = False


class ProviderBadRequest(ProviderError):
    error_class = "bad_request"
    retryable = False


class ProviderMalformedResponse(ProviderError):
    error_class = "malformed_response"
    retryable = False


class Provider(Protocol):
    def generate(self, request: ProviderRequest) -> ProviderResponse: ...
