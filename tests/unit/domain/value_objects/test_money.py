from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import pytest

from braunprices.domain.errors import CurrencyMismatchError, InvalidMoneyError, UnknownCurrencyError
from braunprices.domain.value_objects.currency import EUR, Currency
from braunprices.domain.value_objects.money import Money

USD = Currency.of("USD")
JPY = Currency.of("JPY")


# -- construção ------------------------------------------------------------


def test_normalises_scale_so_that_59_equals_59_00() -> None:
    assert Money.of(59) == Money.of(Decimal("59.00"))


def test_accepts_neutral_string_as_it_arrives_from_json_ld() -> None:
    assert Money.of("1299.99").amount == Decimal("1299.99")


def test_rejects_negative_amount() -> None:
    with pytest.raises(InvalidMoneyError, match="negativo"):
        Money.of(Decimal("-1.00"))


def test_rejects_more_decimals_than_the_currency_admits() -> None:
    with pytest.raises(InvalidMoneyError, match="casas decimais"):
        Money.of(Decimal("59.999"))


def test_rejects_non_finite_amount() -> None:
    with pytest.raises(InvalidMoneyError, match="não finito"):
        Money.of(Decimal("NaN"))


def test_rejects_unreadable_amount() -> None:
    with pytest.raises(InvalidMoneyError, match="ilegível"):
        Money.of("dois euros")


def test_jpy_admits_no_decimals() -> None:
    assert Money.of(1500, JPY).amount == Decimal("1500")
    with pytest.raises(InvalidMoneyError, match="casas decimais"):
        Money.of(Decimal("1500.5"), JPY)


def test_unknown_currency_is_refused_rather_than_assumed() -> None:
    with pytest.raises(UnknownCurrencyError):
        Currency.of("XYZ")


# -- arredondamento explícito ---------------------------------------------


def test_rounded_requires_an_explicit_call_and_honours_the_mode() -> None:
    assert Money.rounded(Decimal("59.995")).amount == Decimal("60.00")
    assert Money.rounded(Decimal("59.995"), rounding=ROUND_DOWN).amount == Decimal("59.99")
    assert Money.rounded(Decimal("59.994"), rounding=ROUND_HALF_UP).amount == Decimal("59.99")


# -- from_pt_string --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("59,00 €", Decimal("59.00")),
        ("59,00€", Decimal("59.00")),
        ("€59,00", Decimal("59.00")),
        ("€ 59,00", Decimal("59.00")),
        ("59,00 EUR", Decimal("59.00")),
        ("  59,00 €  ", Decimal("59.00")),
        ("59,9 €", Decimal("59.90")),
        ("59 €", Decimal("59.00")),
        ("0,99 €", Decimal("0.99")),
    ],
)
def test_reads_simple_portuguese_prices(text: str, expected: Decimal) -> None:
    assert Money.from_pt_string(text).amount == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.299,99 €", Decimal("1299.99")),
        ("1.299,99€", Decimal("1299.99")),
        ("12.345.678,90 €", Decimal("12345678.90")),
        ("1.299 €", Decimal("1299.00")),
    ],
)
def test_reads_thousands_separated_by_dot(text: str, expected: Decimal) -> None:
    assert Money.from_pt_string(text).amount == expected


@pytest.mark.parametrize(
    ("separator", "name"),
    [
        ("\u0020", "espaco"),
        ("\u00a0", "nao separavel"),
        ("\u202f", "nao separavel estreito"),
        ("\u2007", "espaco de algarismo"),
        ("\u2009", "espaco fino"),
    ],
)
def test_reads_thousands_separated_by_the_many_kinds_of_space(separator: str, name: str) -> None:
    # O nao separavel e o caso classico: e invisivel na inspecao do HTML e e a razao
    # pela qual um parser que "devia funcionar" devolve o preco errado.
    read = Money.from_pt_string(f"1{separator}299,99{separator}\u20ac")
    assert read.amount == Decimal("1299.99"), name


@pytest.mark.parametrize("separator", ["\u0020", "\u00a0", "\u202f", "\u2009"])
def test_reads_a_space_between_the_number_and_the_symbol(separator: str) -> None:
    assert Money.from_pt_string(f"59,00{separator}\u20ac").amount == Decimal("59.00")


def test_refuses_the_neutral_format_instead_of_guessing() -> None:
    # "59.00" em português não é cinquenta e nove: o ponto agrupa milhares. Falhar
    # aqui é melhor do que gravar 5900 ou 59 conforme o palpite.
    with pytest.raises(InvalidMoneyError, match="mal agrupado"):
        Money.from_pt_string("59.00 €")


@pytest.mark.parametrize(
    "text",
    ["", "   ", "€", "abc €", "59,00,00 €", "-59,00 €", "59,999 €", "1.29,99 €", ",99 €"],
)
def test_rejects_malformed_text(text: str) -> None:
    with pytest.raises(InvalidMoneyError):
        Money.from_pt_string(text)


def test_rejects_text_whose_symbol_contradicts_the_requested_currency() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money.from_pt_string("59,00 €", USD)


# -- comparação e aritmética ----------------------------------------------


def test_compares_within_the_same_currency() -> None:
    assert Money.of(10) < Money.of(20)
    assert Money.of(20) > Money.of(10)
    assert Money.of(10) <= Money.of(10)
    assert Money.of(10) >= Money.of(10)


def test_min_over_a_series_picks_the_lowest() -> None:
    assert min([Money.of(20), Money.of(9), Money.of(15)]) == Money.of(9)


@pytest.mark.parametrize(
    "operation",
    [
        lambda a, b: a < b,
        lambda a, b: a > b,
        lambda a, b: a <= b,
        lambda a, b: a >= b,
        lambda a, b: a + b,
        lambda a, b: a - b,
    ],
)
def test_refuses_to_mix_currencies(operation: object) -> None:
    euros, dollars = Money.of(10, EUR), Money.of(10, USD)
    with pytest.raises(CurrencyMismatchError):
        operation(euros, dollars)  # type: ignore[operator]


def test_equality_distinguishes_currency() -> None:
    assert Money.of(10, EUR) != Money.of(10, USD)


def test_addition_and_subtraction_stay_in_the_currency() -> None:
    assert Money.of("10.50") + Money.of("4.50") == Money.of("15.00")
    assert Money.of("10.50") - Money.of("0.50") == Money.of("10.00")


def test_subtraction_below_zero_is_refused() -> None:
    with pytest.raises(InvalidMoneyError, match="negativo"):
        Money.of(1) - Money.of(2)


# -- apresentação ----------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("59.00", "59,00\u00a0€"),
        ("1299.99", "1.299,99\u00a0€"),
        ("12345678.90", "12.345.678,90\u00a0€"),
        ("0.99", "0,99\u00a0€"),
    ],
)
def test_formats_back_to_portuguese(amount: str, expected: str) -> None:
    # Espaço não separável antes do símbolo: convenção tipográfica portuguesa.
    assert Money.of(amount).format_pt() == expected


def test_round_trips_through_the_portuguese_format() -> None:
    original = Money.of("1299.99")
    assert Money.from_pt_string(original.format_pt()) == original


def test_is_hashable_so_it_can_live_in_sets() -> None:
    assert len({Money.of(10), Money.of(Decimal("10.00")), Money.of(20)}) == 2


def test_rounded_also_refuses_unreadable_input() -> None:
    with pytest.raises(InvalidMoneyError, match="ilegível"):
        Money.rounded("dois euros")


def test_a_decimal_part_that_is_not_digits_is_refused() -> None:
    with pytest.raises(InvalidMoneyError, match="decimal inválida"):
        Money.from_pt_string("59,0a €")


def test_text_without_any_currency_symbol_is_read_in_the_requested_currency() -> None:
    assert Money.from_pt_string("1.299,99") == Money.of("1299.99")


def test_a_currency_without_decimals_formats_without_a_comma() -> None:
    assert Money.of(1500, JPY).format_pt() == "1.500\u00a0JPY"


def test_str_is_the_portuguese_format() -> None:
    assert str(Money.of("1299.99")) == "1.299,99\u00a0€"
