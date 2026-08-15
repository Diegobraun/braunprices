import pytest

from braunprices.domain.errors import InvalidEANError
from braunprices.domain.value_objects.ean import EAN

# Códigos reais, com dígito de controlo válido.
VALID_EAN_13 = "4006381333931"
VALID_EAN_8 = "96385074"
VALID_UPC_A = "036000291452"


def test_accepts_a_valid_ean_13() -> None:
    assert EAN(VALID_EAN_13).value == VALID_EAN_13


def test_accepts_a_valid_ean_8() -> None:
    ean = EAN(VALID_EAN_8)
    assert ean.value == VALID_EAN_8
    assert ean.length == 8


def test_normalises_upc_a_to_ean_13_so_that_stores_can_match() -> None:
    # Sem esta normalização, uma loja que publica o UPC de 12 dígitos e outra que
    # publica o EAN-13 equivalente nunca casariam o mesmo produto.
    ean = EAN(VALID_UPC_A)
    assert ean.value == "0" + VALID_UPC_A
    assert ean.length == 13


def test_the_normalised_upc_equals_the_ean_13_written_directly() -> None:
    assert EAN(VALID_UPC_A) == EAN("0" + VALID_UPC_A)


@pytest.mark.parametrize(
    "raw",
    [" 4006381333931 ", "4006381333931\n", "400-638-133-3931", "4 006 381 333 931"],
)
def test_tolerates_separators_and_surrounding_space(raw: str) -> None:
    assert EAN(raw).value == VALID_EAN_13


def test_rejects_a_wrong_check_digit() -> None:
    # Último dígito trocado de 1 para 2: um erro de leitura que produziria um
    # casamento errado entre lojas, não um produto obviamente inválido.
    with pytest.raises(InvalidEANError, match="Dígito de controlo"):
        EAN("4006381333932")


def test_rejects_a_transposition_that_breaks_the_checksum() -> None:
    with pytest.raises(InvalidEANError, match="Dígito de controlo"):
        EAN("4006381333391")


@pytest.mark.parametrize("raw", ["", "   ", "12345", "12345678901234567", "400638133393"])
def test_rejects_wrong_lengths(raw: str) -> None:
    with pytest.raises(InvalidEANError):
        EAN(raw)


@pytest.mark.parametrize("raw", ["400638133393X", "abcdefghijklm", "4006381 33393a"])
def test_rejects_non_digits(raw: str) -> None:
    with pytest.raises(InvalidEANError, match="dígitos"):
        EAN(raw)


def test_gtin_14_is_out_of_scope() -> None:
    # 14 dígitos identifica caixa ou palete, não o artigo que se compra online.
    with pytest.raises(InvalidEANError, match="14 dígitos"):
        EAN("14006381333938")


def test_is_hashable_and_compares_by_value() -> None:
    assert len({EAN(VALID_EAN_13), EAN(" 4006381333931 ")}) == 1


def test_string_representation_is_the_normalised_digits() -> None:
    assert str(EAN(VALID_UPC_A)) == "0036000291452"
