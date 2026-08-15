"""Acesso às fixtures de HTML real, sem rede.

As fixtures são capturas verdadeiras de páginas de loja, guardadas comprimidas em
``tests/fixtures/html/``. Nenhum teste desta camada faz um pedido: a página que se
analisa é a que a loja serviu no dia da captura, e não a de hoje — o que torna os
testes repetíveis e independentes de a loja estar de pé.
"""

import gzip
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parents[2] / "fixtures" / "html"

WORTEN_INK_CARTRIDGE = "worten-tinteiro-hp-971-5513302-2026-08-15.html.gz"
WORTEN_TONER = "worten-toner-hp-651a-5844239-2026-08-15.html.gz"
WORTEN_ROBOTS = "worten-robots-2026-08-15.txt"


def load_html(name: str) -> str:
    """Lê uma fixture de HTML, descomprimindo-a."""
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as handle:
        return handle.read()


def load_text(name: str) -> str:
    """Lê uma fixture de texto simples, como um robots.txt."""
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def worten_product_html() -> str:
    """Página de produto real da Worten, com JSON-LD completo."""
    return load_html(WORTEN_INK_CARTRIDGE)


@pytest.fixture
def worten_second_product_html() -> str:
    """Segunda página real, para confirmar que a extração não é ajustada a uma só."""
    return load_html(WORTEN_TONER)


@pytest.fixture
def worten_robots_txt() -> str:
    """O robots.txt real da Worten à data da captura."""
    return load_text(WORTEN_ROBOTS)
