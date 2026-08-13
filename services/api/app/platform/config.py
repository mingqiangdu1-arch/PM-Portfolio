from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _read_secret(name: str) -> str | None:
    direct_value = os.getenv(name)
    file_name = os.getenv(f"{name}_FILE")
    if direct_value and file_name:
        raise ValueError(f"Configure only one of {name} or {name}_FILE")
    if file_name:
        return Path(file_name).read_text(encoding="utf-8").strip()
    return direct_value


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_env: str = "local"
    app_name: str = "ai-product-design-validation-api"
    app_release: str = "0.1.0-dev"
    log_level: str = "INFO"
    docs_enabled: bool = True
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    database_url: str | None = Field(default=None, repr=False)
    redis_password: str | None = Field(default=None, repr=False)
    object_storage_access_key: str | None = Field(default=None, repr=False)
    object_storage_secret_key: str | None = Field(default=None, repr=False)
    access_jwt_secret: str | None = Field(default=None, repr=False)
    upload_signing_secret: str | None = Field(default=None, repr=False)
    internal_service_jwt_secret: str | None = Field(default=None, repr=False)
    ai_api_url: str | None = None
    access_jwt_ttl_seconds: int = 900
    object_storage_endpoint: str = "http://minio:9000"
    object_storage_bucket: str = "product-files"
    object_storage_region: str = "us-east-1"

    @field_validator("app_env")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"local", "ci", "staging", "production", "test"}
        if value not in allowed:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed)}")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.getenv("APP_ENV", "local")
    origins = tuple(
        item.strip()
        for item in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if item.strip()
    )
    return Settings(
        app_env=env,
        app_name=os.getenv("APP_NAME", "ai-product-design-validation-api"),
        app_release=os.getenv("APP_RELEASE", "0.1.0-dev"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        docs_enabled=os.getenv("DOCS_ENABLED", "true").lower() in {"1", "true", "yes"},
        cors_allowed_origins=origins,
        database_url=_read_secret("DATABASE_URL"),
        redis_password=_read_secret("REDIS_PASSWORD"),
        object_storage_access_key=_read_secret("OBJECT_STORAGE_ACCESS_KEY"),
        object_storage_secret_key=_read_secret("OBJECT_STORAGE_SECRET_KEY"),
        access_jwt_secret=_read_secret("ACCESS_JWT_SECRET"),
        upload_signing_secret=_read_secret("UPLOAD_SIGNING_SECRET"),
        internal_service_jwt_secret=_read_secret("INTERNAL_SERVICE_JWT_SECRET"),
        ai_api_url=os.getenv("AI_API_URL"),
        access_jwt_ttl_seconds=int(os.getenv("ACCESS_JWT_TTL_SECONDS", "900")),
        object_storage_endpoint=os.getenv("OBJECT_STORAGE_ENDPOINT", "http://minio:9000"),
        object_storage_bucket=os.getenv("OBJECT_STORAGE_BUCKET", "product-files"),
        object_storage_region=os.getenv("OBJECT_STORAGE_REGION", "us-east-1"),
    )
