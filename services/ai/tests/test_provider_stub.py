import pytest

from app.providers.base import ProviderRateLimited, ProviderRequest, ProviderTimeout, ProviderUnavailable
from app.providers.stub import ProviderStub


def request() -> ProviderRequest:
    return ProviderRequest(
        trace_id="trace-1",
        task_public_id="task-1",
        model="stub-v1",
        prompt_fingerprint="a" * 64,
        input_text="controlled fixture input",
    )


def test_stub_is_deterministic_and_free() -> None:
    first = ProviderStub().generate(request())
    second = ProviderStub().generate(request())
    assert first == second
    assert first.provider == "stub"
    assert first.content.startswith("candidate:")
    assert first.usage.estimated_cost == "0"


@pytest.mark.parametrize(
    ("failure_mode", "error_type", "error_class"),
    [
        ("rate_limited", ProviderRateLimited, "rate_limited"),
        ("timeout", ProviderTimeout, "timeout"),
        ("unavailable", ProviderUnavailable, "unavailable"),
    ],
)
def test_stub_exposes_stable_error_class(failure_mode, error_type, error_class) -> None:
    with pytest.raises(error_type) as caught:
        ProviderStub(failure_mode=failure_mode).generate(request())
    assert caught.value.error_class == error_class
    assert caught.value.retryable is True
