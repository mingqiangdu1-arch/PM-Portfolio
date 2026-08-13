from __future__ import annotations

from hashlib import sha256
from typing import Literal

from app.providers.base import (
    ProviderRateLimited,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeout,
    ProviderUnavailable,
    ProviderUsage,
)


FailureMode = Literal["none", "rate_limited", "timeout", "unavailable"]


class ProviderStub:
    """Deterministic, offline Provider used by local tests and CI only."""

    def __init__(self, *, failure_mode: FailureMode = "none") -> None:
        self.failure_mode = failure_mode

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if self.failure_mode == "rate_limited":
            raise ProviderRateLimited("provider stub rate limit")
        if self.failure_mode == "timeout":
            raise ProviderTimeout("provider stub timeout")
        if self.failure_mode == "unavailable":
            raise ProviderUnavailable("provider stub unavailable")

        digest = sha256(
            f"{request.task_public_id}:{request.prompt_fingerprint}".encode("utf-8")
        ).hexdigest()
        return ProviderResponse(
            provider="stub",
            model=request.model,
            provider_request_id=f"stub-{digest[:24]}",
            content=f"candidate:{digest[:16]}",
            finish_reason="stop",
            usage=ProviderUsage(
                input_tokens=max(1, len(request.input_text.split())),
                output_tokens=1,
                billed_tokens=None,
                estimated_cost="0",
                currency_code="USD",
                cost_source="profile_calculated",
                pricing_version="stub-v1",
            ),
        )
