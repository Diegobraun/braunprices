import dataclasses

import pytest

from braunprices.domain.errors import DomainError
from braunprices.domain.model.store import InvalidRateLimitPolicyError, RateLimitPolicy, Store
from braunprices.domain.value_objects.store_slug import StoreSlug


def store(**kwargs: object) -> Store:
    defaults: dict[str, object] = {
        "slug": StoreSlug("loja-exemplo"),
        "name": "Loja Exemplo",
        "base_domain": "loja-exemplo.pt",
    }
    defaults.update(kwargs)
    return Store(**defaults)  # type: ignore[arg-type]


def test_the_default_policy_is_deliberately_slow() -> None:
    # Uma passagem diária que demore horas é aceitável; uma que a loja registe como
    # pico de tráfego não é.
    policy = RateLimitPolicy()
    assert policy.requests_per_second <= 1
    assert policy.max_concurrency == 1
    assert policy.min_interval_seconds == 2.0


def test_the_minimum_interval_is_the_inverse_of_the_rate() -> None:
    assert RateLimitPolicy(requests_per_second=0.25).min_interval_seconds == 4.0


@pytest.mark.parametrize("rate", [0, -1, 5.1, 100])
def test_a_rate_outside_the_conservative_range_is_refused(rate: float) -> None:
    with pytest.raises(InvalidRateLimitPolicyError, match="requests_per_second"):
        RateLimitPolicy(requests_per_second=rate)


@pytest.mark.parametrize("concurrency", [0, -1, 5, 64])
def test_concurrency_beyond_a_handful_is_refused(concurrency: int) -> None:
    with pytest.raises(InvalidRateLimitPolicyError, match="max_concurrency"):
        RateLimitPolicy(max_concurrency=concurrency)


def test_a_backoff_base_below_one_would_not_grow(recwarn: pytest.WarningsRecorder) -> None:
    with pytest.raises(InvalidRateLimitPolicyError, match="backoff"):
        RateLimitPolicy(backoff_base_seconds=0.5)
    assert len(recwarn) == 0


def test_a_non_positive_timeout_is_refused() -> None:
    with pytest.raises(InvalidRateLimitPolicyError, match="timeout"):
        RateLimitPolicy(timeout_seconds=0)


def test_negative_retries_are_refused() -> None:
    with pytest.raises(InvalidRateLimitPolicyError, match="max_retries"):
        RateLimitPolicy(max_retries=-1)


def test_the_domain_is_normalised_to_lowercase() -> None:
    assert store(base_domain="  Loja-Exemplo.PT ").base_domain == "loja-exemplo.pt"


@pytest.mark.parametrize(
    "domain",
    ["https://loja-exemplo.pt", "loja-exemplo.pt/produtos", "loja exemplo.pt", "  "],
)
def test_the_base_domain_is_only_the_domain(domain: str) -> None:
    with pytest.raises(DomainError, match="base_domain"):
        store(base_domain=domain)


def test_a_store_needs_a_name() -> None:
    with pytest.raises(DomainError, match="nome"):
        store(name="   ")


def test_a_store_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        store().name = "Outro"  # type: ignore[misc]
