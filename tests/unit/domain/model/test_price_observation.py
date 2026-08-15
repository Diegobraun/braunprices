import dataclasses
from datetime import date

import pytest

from braunprices.domain.errors import DomainError
from braunprices.domain.model.availability import Availability
from braunprices.domain.value_objects.money import Money
from tests.unit.domain.conftest import observation


def test_an_observation_cannot_be_changed_after_it_exists() -> None:
    # A imutabilidade é a razão pela qual as afirmações públicas do sistema valem
    # alguma coisa. Um histórico editável não prova nada sobre ninguém.
    existing = observation(day="2026-07-01", price="59.99")
    with pytest.raises(dataclasses.FrozenInstanceError):
        existing.price = Money.of("1.00")  # type: ignore[misc]


def test_correcting_a_price_means_creating_another_observation() -> None:
    original = observation(day="2026-07-01", price="59.99")
    corrected = dataclasses.replace(original, price=Money.of("69.99"))
    assert original.price == Money.of("59.99")
    assert corrected.price == Money.of("69.99")


def test_the_local_date_comes_from_the_lisbon_calendar() -> None:
    assert observation(day="2026-07-12", price="10.00", hour=23).local_date == date(2026, 7, 12)


@pytest.mark.parametrize(
    ("availability", "counts"),
    [
        (Availability.IN_STOCK, True),
        (Availability.LIMITED_AVAILABILITY, True),
        (Availability.PRE_ORDER, True),
        (Availability.BACK_ORDER, True),
        (Availability.OUT_OF_STOCK, False),
        (Availability.SOLD_OUT, False),
        (Availability.DISCONTINUED, False),
        (Availability.UNKNOWN, False),
    ],
)
def test_whether_the_observation_counts_as_a_price_practised(
    availability: Availability, counts: bool
) -> None:
    single = observation(day="2026-07-01", price="10.00", availability=availability)
    assert single.counts_as_price_practised is counts


def test_an_observation_without_provenance_is_refused() -> None:
    # Sem raw_hash não se consegue verificar mais tarde de que conteúdo saiu o número.
    with pytest.raises(DomainError, match="raw_hash"):
        dataclasses.replace(observation(day="2026-07-01", price="10.00"), raw_hash="  ")


def test_a_relative_source_url_is_refused() -> None:
    with pytest.raises(DomainError, match="URL absoluto"):
        dataclasses.replace(observation(day="2026-07-01", price="10.00"), source_url="/p/12345")


def test_two_observations_with_the_same_content_are_equal() -> None:
    assert observation(day="2026-07-01", price="10.00") == observation(
        day="2026-07-01", price="10.00"
    )


def test_is_hashable_so_it_can_be_deduplicated() -> None:
    same = [observation(day="2026-07-01", price="10.00") for _ in range(3)]
    assert len(set(same)) == 1
