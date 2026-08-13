"""Small HS256 service-JWT boundary with no token or secret logging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import hashlib
import hmac
import json
import secrets
from typing import Any, Iterable


class ServiceJwtError(ValueError):
    def __init__(self, code: str, *, status_code: int = 401) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ServicePrincipal:
    issuer: str
    subject: str
    audience: str
    scopes: frozenset[str]
    jwt_id: str
    issued_at: int
    expires_at: int
    task_id: str | None = None
    trace_id: str | None = None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ServiceJwtError("SERVICE_TOKEN_MALFORMED") from exc


def _json_part(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_b64decode(value))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceJwtError("SERVICE_TOKEN_MALFORMED") from exc
    if not isinstance(decoded, dict):
        raise ServiceJwtError("SERVICE_TOKEN_MALFORMED")
    return decoded


def _scopes(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        parts = value.split()
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        parts = value
    else:
        raise ServiceJwtError("SERVICE_TOKEN_MALFORMED")
    return frozenset(part for part in parts if part)


class ServiceJwtVerifier:
    def __init__(
        self,
        *,
        secret: str,
        audience: str,
        allowed_issuers: Iterable[str],
        max_ttl_seconds: int = 300,
        clock_skew_seconds: int = 5,
    ) -> None:
        if not secret:
            raise ValueError("service JWT secret is required")
        self._secret = secret.encode("utf-8")
        self._audience = audience
        self._allowed_issuers = frozenset(allowed_issuers)
        self._max_ttl_seconds = max_ttl_seconds
        self._clock_skew_seconds = clock_skew_seconds

    def verify(
        self,
        token: str,
        *,
        required_scopes: Iterable[str] = (),
        task_id: str | None = None,
        now: datetime | None = None,
    ) -> ServicePrincipal:
        parts = token.split(".")
        if len(parts) != 3:
            raise ServiceJwtError("SERVICE_TOKEN_MALFORMED")
        header = _json_part(parts[0])
        claims = _json_part(parts[1])
        if header.get("alg") != "HS256" or header.get("typ") not in {None, "JWT"}:
            raise ServiceJwtError("SERVICE_TOKEN_ALGORITHM_REJECTED")
        try:
            signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        except UnicodeEncodeError as exc:
            raise ServiceJwtError("SERVICE_TOKEN_MALFORMED") from exc
        expected = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(parts[2])):
            raise ServiceJwtError("SERVICE_TOKEN_SIGNATURE_INVALID")

        issuer = claims.get("iss")
        subject = claims.get("sub")
        jwt_id = claims.get("jti")
        if issuer not in self._allowed_issuers:
            raise ServiceJwtError("SERVICE_TOKEN_ISSUER_INVALID")
        if not isinstance(subject, str) or not subject or not isinstance(jwt_id, str) or not jwt_id:
            raise ServiceJwtError("SERVICE_TOKEN_MALFORMED")
        audience_claim = claims.get("aud")
        if isinstance(audience_claim, str):
            audiences = {audience_claim}
        elif isinstance(audience_claim, list) and all(isinstance(item, str) for item in audience_claim):
            audiences = set(audience_claim)
        else:
            raise ServiceJwtError("SERVICE_TOKEN_MALFORMED")
        if self._audience not in audiences:
            raise ServiceJwtError("SERVICE_TOKEN_AUDIENCE_INVALID")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(issued_at, int) or not isinstance(expires_at, int) or expires_at <= issued_at:
            raise ServiceJwtError("SERVICE_TOKEN_MALFORMED")
        current = int((now or datetime.now(UTC)).timestamp())
        if current >= expires_at + self._clock_skew_seconds:
            raise ServiceJwtError("SERVICE_TOKEN_EXPIRED")
        if issued_at > current + self._clock_skew_seconds:
            raise ServiceJwtError("SERVICE_TOKEN_NOT_YET_VALID")
        if expires_at - issued_at > self._max_ttl_seconds:
            raise ServiceJwtError("SERVICE_TOKEN_TTL_EXCEEDED")
        scopes = _scopes(claims.get("scope"))
        if not set(required_scopes).issubset(scopes):
            raise ServiceJwtError("SERVICE_SCOPE_FORBIDDEN", status_code=403)
        claim_task_id = claims.get("task_id")
        if task_id is not None and claim_task_id != task_id:
            raise ServiceJwtError("SERVICE_TASK_SCOPE_FORBIDDEN", status_code=403)
        return ServicePrincipal(
            issuer=issuer,
            subject=subject,
            audience=self._audience,
            scopes=scopes,
            jwt_id=jwt_id,
            issued_at=issued_at,
            expires_at=expires_at,
            task_id=claim_task_id,
            trace_id=claims.get("trace_id"),
        )


class ServiceJwtIssuer:
    def __init__(self, *, secret: str, issuer: str, subject: str, audience: str, ttl_seconds: int = 120) -> None:
        if not secret:
            raise ValueError("service JWT secret is required")
        if not 1 <= ttl_seconds <= 300:
            raise ValueError("service JWT TTL must be between 1 and 300 seconds")
        self._secret = secret.encode("utf-8")
        self._issuer = issuer
        self._subject = subject
        self._audience = audience
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        scopes: Iterable[str],
        task_id: str | None = None,
        trace_id: str | None = None,
        now: datetime | None = None,
        jwt_id: str | None = None,
    ) -> str:
        issued_at = int((now or datetime.now(UTC)).timestamp())
        claims: dict[str, Any] = {
            "iss": self._issuer,
            "sub": self._subject,
            "aud": self._audience,
            "scope": " ".join(sorted(set(scopes))),
            "jti": jwt_id or secrets.token_urlsafe(18),
            "iat": issued_at,
            "exp": issued_at + self._ttl_seconds,
        }
        if task_id is not None:
            claims["task_id"] = task_id
        if trace_id is not None:
            claims["trace_id"] = trace_id
        header = {"alg": "HS256", "typ": "JWT"}
        encoded_header = _b64encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
        encoded_claims = _b64encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
        signature = hmac.new(self._secret, f"{encoded_header}.{encoded_claims}".encode("ascii"), hashlib.sha256).digest()
        return f"{encoded_header}.{encoded_claims}.{_b64encode(signature)}"
