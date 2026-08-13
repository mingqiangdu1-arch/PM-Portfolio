from decimal import Decimal

from app.providers.openai_compatible import ModelPrice, OpenAICompatibleProfile


def deepseek_profile() -> OpenAICompatibleProfile:
    """DeepSeek OpenAI-compatible V4 profile; contains no credential."""

    return OpenAICompatibleProfile(
        profile_id="deepseek",
        base_url="https://api.deepseek.com",
        allowed_models=("deepseek-v4-flash", "deepseek-v4-pro"),
        timeout_seconds=60.0,
        pricing_version="2026-07-29",
        prices={
            "deepseek-v4-flash": ModelPrice(
                cached_input_per_million=Decimal("0.0028"),
                uncached_input_per_million=Decimal("0.14"),
                output_per_million=Decimal("0.28"),
            ),
            "deepseek-v4-pro": ModelPrice(
                cached_input_per_million=Decimal("0.003625"),
                uncached_input_per_million=Decimal("0.435"),
                output_per_million=Decimal("0.87"),
            ),
        },
    )
