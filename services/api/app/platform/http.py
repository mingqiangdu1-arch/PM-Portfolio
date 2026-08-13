from typing import Annotated

from fastapi import Header

from app.platform.errors import ApiError


async def require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if idempotency_key is None or not 8 <= len(idempotency_key) <= 128:
        raise ApiError(
            code="IDEMPOTENCY_KEY_REQUIRED",
            message="Idempotency-Key must contain 8 to 128 characters",
        )
    return idempotency_key
