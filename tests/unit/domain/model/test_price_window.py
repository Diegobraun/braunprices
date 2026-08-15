from datetime import date, datetime

import pytest

from braunprices.domain.errors import InvalidPriceWindowError
from braunprices.domain.model.price_window import DEFAULT_WINDOW_DAYS, PriceWindow

REFERENCE = date(2026, 7, 12)


def test_the_default_window_is_the_thirty_days_the_law_names() -> None:
    assert DEFAULT_WINDOW_DAYS == 30
    assert PriceWindow(REFERENCE).window_days == 30


def test_the_window_starts_thirty_days_before_the_reference() -> None:
    assert PriceWindow(REFERENCE).start == date(2026, 6, 12)


def test_the_window_ends_on_the_reference_day_exclusive() -> None:
    # "Anteriores" exclui o dia da aplicação do desconto.
    assert PriceWindow(REFERENCE).end_exclusive == REFERENCE
    assert not PriceWindow(REFERENCE).contains(REFERENCE)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 6, 11), False),  # véspera do início
        (date(2026, 6, 12), True),  # primeiro dia
        (date(2026, 6, 30), True),  # meio
        (date(2026, 7, 11), True),  # último dia
        (date(2026, 7, 12), False),  # dia de referência
        (date(2026, 7, 13), False),  # depois
    ],
)
def test_containment_at_and_around_both_edges(day: date, expected: bool) -> None:
    assert PriceWindow(REFERENCE).contains(day) is expected


def test_the_window_crosses_month_and_year_boundaries() -> None:
    window = PriceWindow(date(2027, 1, 5))
    assert window.start == date(2026, 12, 6)
    assert window.contains(date(2026, 12, 31))
    assert window.contains(date(2027, 1, 1))


def test_the_window_handles_a_leap_day() -> None:
    window = PriceWindow(date(2028, 3, 10))
    assert window.start == date(2028, 2, 9)
    assert window.contains(date(2028, 2, 29))


@pytest.mark.parametrize("days", [0, -1, -30])
def test_a_window_shorter_than_a_day_is_refused(days: int) -> None:
    with pytest.raises(InvalidPriceWindowError, match="não é uma janela"):
        PriceWindow(REFERENCE, window_days=days)


def test_a_reference_that_is_not_a_date_is_refused() -> None:
    with pytest.raises(InvalidPriceWindowError, match="date"):
        PriceWindow("2026-07-12")  # type: ignore[arg-type]


def test_a_datetime_is_refused_even_though_it_is_a_date_subclass() -> None:
    # datetime passa num isinstance(date) e traz uma hora que a janela não usa,
    # criando a ilusão de que a fronteira é ao instante e não ao dia.
    with pytest.raises(InvalidPriceWindowError, match="datetime"):
        PriceWindow(datetime(2026, 7, 12, 10, 0))  # noqa: DTZ001


def test_it_reads_as_a_half_open_interval() -> None:
    assert str(PriceWindow(REFERENCE)) == "[2026-06-12, 2026-07-12)"


def test_is_hashable_and_compares_by_value() -> None:
    assert PriceWindow(REFERENCE) == PriceWindow(REFERENCE, window_days=30)
    assert len({PriceWindow(REFERENCE), PriceWindow(REFERENCE)}) == 1
