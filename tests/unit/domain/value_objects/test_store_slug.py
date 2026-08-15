import pytest

from braunprices.domain.errors import InvalidStoreSlugError
from braunprices.domain.value_objects.store_slug import StoreSlug


@pytest.mark.parametrize("raw", ["worten", "el-corte-ingles", "fnac", "pc-diga", "loja123", "a1"])
def test_accepts_well_formed_slugs(raw: str) -> None:
    assert StoreSlug(raw).value == raw


def test_trims_surrounding_space() -> None:
    assert StoreSlug("  worten  ").value == "worten"


@pytest.mark.parametrize(
    "raw",
    [
        "Worten",  # maiúsculas
        "el corte ingles",  # espaço interior
        "-worten",  # hífen à cabeça
        "worten-",  # hífen no fim
        "worten_pt",  # underscore
        "worten.pt",  # ponto
        "a",  # curto demais
        "",  # vazio
        "x" * 51,  # comprido demais
        "loja/pt",  # barra
        "wörten",  # acentuado
    ],
)
def test_rejects_malformed_slugs(raw: str) -> None:
    with pytest.raises(InvalidStoreSlugError):
        StoreSlug(raw)


def test_compares_by_value_and_is_hashable() -> None:
    assert StoreSlug("worten") == StoreSlug("worten")
    assert len({StoreSlug("worten"), StoreSlug("worten"), StoreSlug("fnac")}) == 2


def test_string_representation_is_the_slug_itself() -> None:
    # O slug aparece em URLs públicos da API, logo o str() tem de ser o valor cru.
    assert str(StoreSlug("worten")) == "worten"
