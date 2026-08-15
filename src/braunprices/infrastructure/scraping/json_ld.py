"""Extração de ``schema.org/Product`` a partir de JSON-LD.

É a fonte primária porque é a que a loja publica *de propósito* para ser lida por
máquinas: muda menos que o HTML de apresentação e é a mesma em todo o catálogo. Ver
ADR-0004.

Este módulo trata o conteúdo da página como **dado a analisar, nunca como instrução**.
Nada do que vem daqui é executado, interpretado como comando, ou usado para construir
caminhos ou consultas. Se um bloco JSON-LD contiver algo que se pareça com instruções,
é apenas texto num campo.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from selectolax.parser import HTMLParser

from braunprices.domain.errors import DomainError
from braunprices.domain.model.availability import Availability
from braunprices.domain.model.scrape_outcome import FailureReason, ScrapeFailure
from braunprices.domain.value_objects.currency import Currency
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.money import Money

# Mapeamento de ``schema.org/ItemAvailability``. Aceita as formas com http e https, e
# com ou sem prefixo, porque as três aparecem em lojas reais.
_AVAILABILITY_BY_SCHEMA_TERM = {
    "instock": Availability.IN_STOCK,
    "outofstock": Availability.OUT_OF_STOCK,
    "soldout": Availability.SOLD_OUT,
    "preorder": Availability.PRE_ORDER,
    "presale": Availability.PRE_ORDER,
    "backorder": Availability.BACK_ORDER,
    "limitedavailability": Availability.LIMITED_AVAILABILITY,
    "discontinued": Availability.DISCONTINUED,
    "instoreonly": Availability.LIMITED_AVAILABILITY,
    "onlineonly": Availability.IN_STOCK,
}

# Campos onde o código de barras aparece, por ordem de preferência.
_GTIN_FIELDS = ("gtin13", "gtin", "gtin12", "gtin8", "ean")


@dataclass(frozen=True, slots=True)
class ProductMarkup:
    """O que o JSON-LD de um produto declarou, já validado pelo domínio."""

    name: str
    price: Money
    availability: Availability
    ean: EAN | None
    sku: str | None


def extract_product(html: str) -> ProductMarkup | ScrapeFailure:
    """Lê o primeiro bloco ``schema.org/Product`` utilizável de uma página.

    Devolve uma falha classificada em vez de levantar exceção: uma página cuja
    marcação mudou é um acontecimento previsto e que interessa contar, não um erro de
    programação.
    """
    blocks = _json_ld_blocks(html)
    if not blocks:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_MISSING,
            detail="A página não tem nenhum bloco application/ld+json.",
        )

    products = [node for block in blocks for node in _walk_for_products(block)]
    if not products:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_MISSING,
            detail=f"Nenhum dos {len(blocks)} blocos JSON-LD declara @type Product.",
        )

    return _to_markup(products[0])


def _json_ld_blocks(html: str) -> list[object]:
    """Devolve os blocos JSON-LD que são JSON válido, ignorando os que não são.

    Um bloco malformado não invalida a página: é comum haver vários, e basta que um
    sirva. Se nenhum servir, quem chama recebe a falha.
    """
    tree = HTMLParser(html)
    blocks: list[object] = []
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text()
        if not raw or not raw.strip():
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def _walk_for_products(node: object) -> list[dict[str, Any]]:
    """Encontra nós ``@type: Product``, incluindo dentro de ``@graph`` e de listas.

    O parâmetro é ``object`` de propósito: isto percorre JSON vindo de uma página, cuja
    forma não controlamos e sobre a qual não se pode assumir coisa nenhuma. Cada ramo
    verifica o tipo antes de o usar.
    """
    found: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_walk_for_products(item))
        return found
    if not isinstance(node, dict):
        return found
    if _declares_type(node, "Product"):
        found.append(node)
    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in node:
            found.extend(_walk_for_products(node[key]))
    return found


def _declares_type(node: dict[str, Any], wanted: str) -> bool:
    declared = node.get("@type")
    if isinstance(declared, str):
        return declared.split("/")[-1].lower() == wanted.lower()
    if isinstance(declared, list):
        return any(
            isinstance(item, str) and item.split("/")[-1].lower() == wanted.lower()
            for item in declared
        )
    return False


def _to_markup(product: dict[str, Any]) -> ProductMarkup | ScrapeFailure:
    name = product.get("name")
    if not isinstance(name, str) or not name.strip():
        return ScrapeFailure(
            reason=FailureReason.MARKUP_INVALID,
            detail="O bloco Product não tem `name` utilizável.",
        )

    offer = _first_offer(product)
    if offer is None:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_MISSING,
            detail=f"O produto {name!r} não declara `offers`.",
        )

    price = _read_price(offer)
    if isinstance(price, ScrapeFailure):
        return price

    return ProductMarkup(
        name=name.strip(),
        price=price,
        availability=_read_availability(offer),
        ean=_read_ean(product),
        sku=_read_sku(product),
    )


def _first_offer(product: dict[str, Any]) -> dict[str, Any] | None:
    """Devolve a primeira oferta declarada.

    Com várias ofertas, a primeira é a da própria loja nas marcações que encontrámos.
    Escolher por valor — a mais barata, por exemplo — arriscaria registar o preço de um
    vendedor terceiro como se fosse o da loja.
    """
    offers = product.get("offers")
    if isinstance(offers, dict):
        return offers if _declares_type(offers, "Offer") or "price" in offers else None
    if isinstance(offers, list):
        for candidate in offers:
            if isinstance(candidate, dict) and "price" in candidate:
                return candidate
    return None


def _read_price(offer: dict[str, Any]) -> Money | ScrapeFailure:
    """Lê o preço da oferta, no formato neutro em que o schema.org o define."""
    raw = offer.get("price")
    if raw is None:
        specification = offer.get("priceSpecification")
        if isinstance(specification, dict):
            raw = specification.get("price")
    if raw is None:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_MISSING,
            detail="A oferta não declara `price`.",
        )

    currency_code = offer.get("priceCurrency") or "EUR"
    try:
        currency = Currency.of(str(currency_code))
        # O schema.org define `price` com ponto decimal, e é assim que chega. Um float
        # seria convertido com o erro de representação binária já lá dentro, pelo que
        # se passa sempre pela forma textual.
        return Money.rounded(Decimal(str(raw).strip()), currency)
    except (DomainError, ArithmeticError, ValueError) as error:
        return ScrapeFailure(
            reason=FailureReason.PRICE_UNREADABLE,
            detail=f"Preço {raw!r} em {currency_code!r} não é utilizável: {error}",
        )


def _read_availability(offer: dict[str, Any]) -> Availability:
    """Traduz ``schema.org/ItemAvailability``, com ``UNKNOWN`` como omissão segura."""
    raw = offer.get("availability")
    if not isinstance(raw, str):
        return Availability.UNKNOWN
    term = raw.rsplit("/", 1)[-1].replace("#", "").strip().lower()
    return _AVAILABILITY_BY_SCHEMA_TERM.get(term, Availability.UNKNOWN)


def _read_ean(product: dict[str, Any]) -> EAN | None:
    """Lê o código de barras, se estiver declarado e for válido.

    Um dígito de controlo errado devolve ``None`` em vez de falhar a extração: o preço
    continua a valer, e o que se perde é a participação no casamento entre lojas.
    """
    for field in _GTIN_FIELDS:
        raw = product.get(field)
        if raw is None:
            continue
        try:
            return EAN(str(raw))
        except DomainError:
            continue
    return None


def _read_sku(product: dict[str, Any]) -> str | None:
    for field in ("sku", "mpn", "productID"):
        raw = product.get(field)
        if isinstance(raw, str | int) and str(raw).strip():
            return str(raw).strip()
    return None
