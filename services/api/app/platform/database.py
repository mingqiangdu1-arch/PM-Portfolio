from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from app.platform.config import get_settings
from app.platform.errors import ApiError


@lru_cache(maxsize=1)
def get_engine() -> Any:
    settings = get_settings()
    if not settings.database_url:
        raise ApiError(
            code="DEPENDENCY_UNAVAILABLE",
            message="Database is not configured",
            http_status=503,
        )
    from sqlalchemy import create_engine

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        isolation_level="READ COMMITTED",
    )


@contextmanager
def transaction() -> Iterator[Any]:
    with get_engine().begin() as connection:
        yield connection


@contextmanager
def readonly() -> Iterator[Any]:
    with get_engine().connect() as connection:
        yield connection
