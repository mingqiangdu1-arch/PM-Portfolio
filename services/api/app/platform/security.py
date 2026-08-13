from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from app.platform.errors import ApiError


def hash_password(password: str) -> str:
    from argon2 import PasswordHasher
    from argon2.low_level import Type

    return PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    ).hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import VerificationError
        from argon2.low_level import Type

        return PasswordHasher(type=Type.ID).verify(password_hash, password)
    except (VerificationError, ValueError):
        return False


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode_b64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def encode_hs256(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    head = _b64(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{signature}"


def decode_hs256(
    token: str,
    secret: str,
    *,
    audience: str,
    issuer: str | None = None,
    required_scope: str | None = None,
    require_jti: bool = False,
    max_ttl_seconds: int | None = None,
    clock_skew_seconds: int = 30,
) -> dict[str, Any]:
    try:
        head, body, supplied = token.split(".")
        expected = _b64(
            hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("signature")
        header = json.loads(_decode_b64(head))
        payload = json.loads(_decode_b64(body))
        now = int(time.time())
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("algorithm")
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
        if payload.get("aud") != audience or expires_at <= now - clock_skew_seconds:
            raise ValueError("claims")
        if issuer is not None and payload.get("iss") != issuer:
            raise ValueError("issuer")
        if issued_at > now + clock_skew_seconds or expires_at <= issued_at:
            raise ValueError("time window")
        if max_ttl_seconds is not None and expires_at - issued_at > max_ttl_seconds:
            raise ValueError("ttl")
        if require_jti and not isinstance(payload.get("jti"), str):
            raise ValueError("jti")
        if require_jti and not payload["jti"]:
            raise ValueError("jti")
        if required_scope is not None and required_scope not in set(str(payload.get("scope", "")).split()):
            raise ValueError("scope")
        return payload
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ApiError(code="AUTH_REQUIRED", message="Invalid or expired access token", http_status=401) from exc


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: int
    session_id: str
    jti: str
    expires_at: int


def issue_access_token(*, user_id: int, session_id: str, secret: str, ttl_seconds: int) -> tuple[str, AccessClaims]:
    now = int(time.time())
    claims = AccessClaims(user_id, session_id, secrets.token_urlsafe(18), now + ttl_seconds)
    payload = {
        "iss": "business-api",
        "sub": str(user_id),
        "aud": "business-api",
        "sid": session_id,
        "jti": claims.jti,
        "iat": now,
        "exp": claims.expires_at,
    }
    return encode_hs256(payload, secret), claims
