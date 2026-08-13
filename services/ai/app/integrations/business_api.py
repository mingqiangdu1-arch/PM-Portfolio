"""Business API health adapter using a short-lived, least-privilege service JWT."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.security import ServiceJwtIssuer


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    status: str
    http_status: int | None = None
    error_class: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "available"


class BusinessApiHealthClient:
    def __init__(
        self,
        *,
        base_url: str,
        token_issuer: ServiceJwtIssuer,
        timeout_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_issuer = token_issuer
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def probe(self, *, trace_id: str) -> DependencyHealth:
        token = self._token_issuer.issue(scopes={"health"}, trace_id=trace_id)
        try:
            with httpx.Client(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = client.get(
                    f"{self._base_url}/internal/v1/health",
                    headers={"Authorization": f"Bearer {token}", "X-Trace-ID": trace_id},
                )
        except httpx.TimeoutException:
            return DependencyHealth("unavailable", error_class="timeout")
        except httpx.HTTPError:
            return DependencyHealth("unavailable", error_class="network")
        if response.status_code == 200:
            return DependencyHealth("available", http_status=200)
        if response.status_code in {401, 403}:
            return DependencyHealth("unavailable", http_status=response.status_code, error_class="authentication")
        return DependencyHealth("unavailable", http_status=response.status_code, error_class="dependency")
