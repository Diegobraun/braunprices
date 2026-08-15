"""A regra central: preço mais baixo praticado nos 30 dias anteriores.

Estes testes existem para os casos onde a implementação ingénua erra. Cada um está
escrito a partir da redação do Decreto-Lei n.º 109-G/2021, não a partir do código.
"""

from datetime import date
from decimal import Decimal

import pytest

from braunprices.domain.errors import CurrencyMismatchError
from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.price_window import PriceWindow
from braunprices.domain.rules.price_reference import (
    lowest_price_in_window,
    observations_in_window,
)
from braunprices.domain.value_objects.currency import Currency
from braunprices.domain.value_objects.money import Money
from tests.unit.domain.conftest import observation

REFERENCE = date(2026, 7, 12)


# -- janela vazia ----------------------------------------------------------


def test_returns_none_when_there_is_nothing_in_the_window() -> None:
    # None é "não sabemos". Zero seria "esteve a custar nada", que é falso, e uma
    # exceção obrigaria quem chama a tratar o caso normal como erro.
    assert lowest_price_in_window([], REFERENCE) is None


def test_returns_none_when_every_observation_falls_outside_the_window() -> None:
    old = [observation(day="2026-05-01", price="10.00")]
    assert lowest_price_in_window(old, REFERENCE) is None


def test_a_stable_series_yields_the_price_it_always_had(
    daily_series: list[PriceObservation],
) -> None:
    assert lowest_price_in_window(daily_series, REFERENCE) == Money.of("59.99")


# -- buracos na série ------------------------------------------------------


def test_days_without_collection_are_not_interpolated() -> None:
    # Entre 20/06 a 100 € e 30/06 a 60 € houve dez dias sem recolha. Um sistema que
    # interpolasse inventaria preços intermédios; este afirma apenas o que viu.
    sparse = [
        observation(day="2026-06-20", price="100.00"),
        observation(day="2026-06-30", price="60.00"),
    ]
    assert lowest_price_in_window(sparse, REFERENCE) == Money.of("60.00")


def test_a_single_observation_in_the_whole_window_is_enough() -> None:
    single = [observation(day="2026-07-01", price="42.50")]
    assert lowest_price_in_window(single, REFERENCE) == Money.of("42.50")


# -- disponibilidade -------------------------------------------------------


def test_out_of_stock_observations_are_not_prices_practised() -> None:
    # Um preço apresentado em produto esgotado não é um preço a que alguém pudesse
    # comprar, e usá-lo como referência baixaria artificialmente o mínimo legal.
    series = [
        observation(day="2026-07-01", price="80.00"),
        observation(day="2026-07-05", price="10.00", availability=Availability.OUT_OF_STOCK),
    ]
    assert lowest_price_in_window(series, REFERENCE) == Money.of("80.00")


@pytest.mark.parametrize(
    "availability",
    [Availability.OUT_OF_STOCK, Availability.SOLD_OUT, Availability.DISCONTINUED],
)
def test_unavailable_states_never_count(availability: Availability) -> None:
    series = [observation(day="2026-07-01", price="10.00", availability=availability)]
    assert lowest_price_in_window(series, REFERENCE) is None


@pytest.mark.parametrize(
    "availability",
    [
        Availability.IN_STOCK,
        Availability.LIMITED_AVAILABILITY,
        Availability.PRE_ORDER,
        Availability.BACK_ORDER,
    ],
)
def test_available_states_count(availability: Availability) -> None:
    series = [observation(day="2026-07-01", price="10.00", availability=availability)]
    assert lowest_price_in_window(series, REFERENCE) == Money.of("10.00")


def test_unknown_availability_does_not_count() -> None:
    # Escolha conservadora: contar uma observação cuja disponibilidade não
    # conseguimos ler seria afirmar um facto que não observámos.
    series = [observation(day="2026-07-01", price="10.00", availability=Availability.UNKNOWN)]
    assert lowest_price_in_window(series, REFERENCE) is None


# -- promoções anteriores contam -------------------------------------------


def test_a_previous_promotion_inside_the_window_counts() -> None:
    # A lei é explícita: os 30 dias incluem períodos que já tenham sido de saldos ou
    # promoções. Excluir a promoção anterior é precisamente a manobra que a norma
    # existe para impedir.
    series = [
        observation(day="2026-06-20", price="100.00"),
        observation(day="2026-06-24", price="49.99"),  # promoção de 4 dias
        observation(day="2026-06-25", price="49.99"),
        observation(day="2026-06-28", price="100.00"),
        observation(day="2026-07-10", price="100.00"),
    ]
    assert lowest_price_in_window(series, REFERENCE) == Money.of("49.99")


# -- fronteira da janela ---------------------------------------------------


def test_the_first_day_of_the_window_is_included() -> None:
    # A janela vai de 12/06 (inclusive) a 12/07 (exclusive): 30 dias anteriores.
    on_the_edge = [observation(day="2026-06-12", price="30.00", hour=0)]
    assert lowest_price_in_window(on_the_edge, REFERENCE) == Money.of("30.00")


def test_the_day_before_the_window_is_excluded() -> None:
    just_outside = [observation(day="2026-06-11", price="30.00", hour=23)]
    assert lowest_price_in_window(just_outside, REFERENCE) is None


def test_the_reference_day_itself_is_excluded() -> None:
    # "Os 30 dias consecutivos anteriores à aplicação do desconto" exclui o próprio
    # dia: incluí-lo deixaria entrar no cálculo o preço já promocional.
    same_day = [observation(day="2026-07-12", price="1.00", hour=0)]
    assert lowest_price_in_window(same_day, REFERENCE) is None


def test_the_last_second_of_the_previous_day_is_included() -> None:
    series = [observation(day="2026-07-11", price="30.00", hour=23)]
    assert lowest_price_in_window(series, REFERENCE) == Money.of("30.00")


def test_the_window_spans_exactly_thirty_distinct_days() -> None:
    every_day = [observation(day=f"2026-06-{day:02d}", price="50.00") for day in range(1, 31)]
    every_day += [observation(day=f"2026-07-{day:02d}", price="50.00") for day in range(1, 13)]

    eligible = observations_in_window(every_day, PriceWindow(REFERENCE))
    assert len({item.local_date for item in eligible}) == 30


def test_the_window_length_is_configurable() -> None:
    series = [
        observation(day="2026-07-01", price="80.00"),
        observation(day="2026-07-10", price="70.00"),
    ]
    assert lowest_price_in_window(series, REFERENCE, window_days=5) == Money.of("70.00")
    assert lowest_price_in_window(series, REFERENCE, window_days=30) == Money.of("70.00")


def test_the_summer_day_boundary_follows_lisbon_not_utc() -> None:
    # 23:30 de 11/07 em Lisboa é 22:30 UTC; se o dia fosse calculado em UTC a
    # observação continuaria no dia 11 e o resultado seria o mesmo. O caso que
    # distingue os dois é a observação às 00:30 locais de 12/07, que em UTC é ainda
    # dia 11 — e que tem de ficar de fora, porque 12/07 é o dia de referência.
    inside = observation(day="2026-07-11", price="30.00", hour=23)
    outside = observation(day="2026-07-12", price="5.00", hour=0)
    assert lowest_price_in_window([inside, outside], REFERENCE) == Money.of("30.00")


# -- moedas ----------------------------------------------------------------


def test_a_series_mixing_currencies_fails_loudly() -> None:
    # Não deve acontecer, mas se acontecer o mínimo não teria significado nenhum.
    dollars = Money.of(Decimal("10.00"), Currency.of("USD"))
    series = [
        observation(day="2026-07-01", price="80.00"),
        observation(day="2026-07-02", price="0", currency_amount=dollars),
    ]
    with pytest.raises(CurrencyMismatchError):
        lowest_price_in_window(series, REFERENCE)


# -- independência da ordem de entrada -------------------------------------


def test_the_result_does_not_depend_on_the_order_the_observations_arrive() -> None:
    series = [
        observation(day="2026-07-05", price="70.00"),
        observation(day="2026-06-20", price="55.00"),
        observation(day="2026-07-01", price="90.00"),
    ]
    assert lowest_price_in_window(series, REFERENCE) == Money.of("55.00")
    assert lowest_price_in_window(list(reversed(series)), REFERENCE) == Money.of("55.00")
