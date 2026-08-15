from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from braunprices.domain.errors import InvalidObservedAtError
from braunprices.domain.value_objects.observed_at import LISBON, ObservedAt


def test_rejects_a_naive_datetime() -> None:
    # Uma hora sem fuso é uma hora sem sítio, e a fronteira de dia deixa de ser
    # determinável — que é exatamente aquilo de que a regra dos 30 dias depende.
    with pytest.raises(InvalidObservedAtError, match="fuso"):
        ObservedAt(datetime(2026, 7, 12, 10, 0))  # noqa: DTZ001


def test_normalises_any_offset_to_utc() -> None:
    lisbon_summer = datetime(2026, 7, 12, 11, 0, tzinfo=timezone(timedelta(hours=1)))
    assert ObservedAt(lisbon_summer).instant == datetime(2026, 7, 12, 10, 0, tzinfo=UTC)


def test_from_lisbon_reads_a_naive_datetime_as_local_time() -> None:
    observed = ObservedAt.from_lisbon(datetime(2026, 7, 12, 11, 0))  # noqa: DTZ001
    assert observed.instant == datetime(2026, 7, 12, 10, 0, tzinfo=UTC)


def test_from_lisbon_refuses_a_datetime_that_already_has_a_zone() -> None:
    with pytest.raises(InvalidObservedAtError, match="sem fuso"):
        ObservedAt.from_lisbon(datetime(2026, 7, 12, 11, 0, tzinfo=UTC))


# -- fronteira de dia ------------------------------------------------------


def test_local_date_follows_lisbon_and_not_utc_in_summer() -> None:
    # No verão Lisboa está em UTC+1: 23:30 UTC já é o dia seguinte em Lisboa.
    # Atribuir este preço ao dia de UTC deslocaria uma observação inteira de janela.
    observed = ObservedAt(datetime(2026, 7, 12, 23, 30, tzinfo=UTC))
    assert observed.local_date == date(2026, 7, 13)


def test_local_date_matches_utc_in_winter() -> None:
    # No inverno Lisboa está em UTC+0 e as duas datas coincidem.
    observed = ObservedAt(datetime(2026, 12, 12, 23, 30, tzinfo=UTC))
    assert observed.local_date == date(2026, 12, 12)


def test_midnight_in_lisbon_belongs_to_the_day_that_starts() -> None:
    observed = ObservedAt.from_lisbon(datetime(2026, 7, 13, 0, 0))  # noqa: DTZ001
    assert observed.local_date == date(2026, 7, 13)


def test_one_second_before_midnight_belongs_to_the_day_that_ends() -> None:
    observed = ObservedAt.from_lisbon(datetime(2026, 7, 12, 23, 59, 59))  # noqa: DTZ001
    assert observed.local_date == date(2026, 7, 12)


def test_spring_forward_night_keeps_the_right_day() -> None:
    # Em 2026 Lisboa avança o relógio a 29 de março: 00:59 UTC ainda é dia 29,
    # e 01:00 UTC passa a ser 02:00 locais, também dia 29.
    before = ObservedAt(datetime(2026, 3, 29, 0, 59, tzinfo=UTC))
    after = ObservedAt(datetime(2026, 3, 29, 1, 0, tzinfo=UTC))
    assert before.local_date == date(2026, 3, 29)
    assert after.local_date == date(2026, 3, 29)
    assert after.local_datetime.hour == 2


def test_fall_back_night_distinguishes_the_two_occurrences_of_the_same_local_hour() -> None:
    # A 25 de outubro de 2026 o relógio recua e 01:30 locais acontece duas vezes.
    # Guardar em UTC é o que permite distingui-las; guardar em hora local não.
    first = ObservedAt(datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    second = ObservedAt(datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert first != second
    assert first < second
    assert first.local_datetime.hour == second.local_datetime.hour == 1
    assert first.local_date == second.local_date == date(2026, 10, 25)


# -- ordenação e igualdade -------------------------------------------------


def test_orders_by_instant_regardless_of_the_offset_it_came_in() -> None:
    utc_ten = ObservedAt(datetime(2026, 7, 12, 10, 0, tzinfo=UTC))
    lisbon_eleven = ObservedAt(datetime(2026, 7, 12, 11, 0, tzinfo=LISBON))
    assert utc_ten == lisbon_eleven  # o mesmo instante, escrito de duas maneiras
    assert not utc_ten < lisbon_eleven


def test_sorts_chronologically() -> None:
    early = ObservedAt(datetime(2026, 7, 12, 8, 0, tzinfo=UTC))
    late = ObservedAt(datetime(2026, 7, 12, 20, 0, tzinfo=UTC))
    assert sorted([late, early]) == [early, late]


def test_is_hashable() -> None:
    moment = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    assert len({ObservedAt(moment), ObservedAt(moment)}) == 1


def test_all_four_comparisons_agree_with_the_underlying_instant() -> None:
    early = ObservedAt(datetime(2026, 7, 12, 8, 0, tzinfo=UTC))
    late = ObservedAt(datetime(2026, 7, 12, 20, 0, tzinfo=UTC))
    same = ObservedAt(datetime(2026, 7, 12, 8, 0, tzinfo=UTC))
    assert early < late
    assert early <= same
    assert late > early
    assert late >= early
    assert not late <= early
    assert not early >= late


def test_str_is_the_utc_instant_in_iso_format() -> None:
    # ISO com fuso explícito: um carimbo sem fuso num log é indecifrável mais tarde.
    assert str(ObservedAt(datetime(2026, 7, 12, 10, 0, tzinfo=UTC))) == "2026-07-12T10:00:00+00:00"
