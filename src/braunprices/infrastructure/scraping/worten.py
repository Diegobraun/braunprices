"""Adaptador da Worten, a primeira loja.

Cadeia de extração:

1. **JSON-LD** (`schema.org/Product`) — a fonte primária. É o que a loja publica de
   propósito para ser lido por máquinas.
2. **Microdados no HTML** — o recurso, usado apenas quando o JSON-LD falta ou está
   inutilizável, e **sempre registado** quando dispara. Ver ADR-0004.

Todos os seletores abaixo foram derivados do HTML real guardado em
``tests/fixtures/html/``, com a data de captura no nome. Nenhum foi escrito de memória.

O fallback tem uma particularidade que veio da inspeção desse HTML e não de suposição:
a página traz **três** elementos ``meta[itemprop="price"]``, e um deles é a oferta de um
vendedor terceiro dentro de ``.product-other-offers__price``. Registar esse valor como
preço da Worten envenenaria o histórico sem que nada rebentasse — que é exatamente o
tipo de falha silenciosa que este projeto existe para evitar. Por isso o fallback
descarta as ofertas de terceiros e, se ainda assim restar mais do que um valor, recusa
em vez de escolher.
"""

import hashlib
from datetime import UTC, datetime

import structlog
from selectolax.parser import HTMLParser

from braunprices.domain.errors import DomainError
from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import StoreListing
from braunprices.domain.model.scrape_outcome import (
    ExtractionSource,
    FailureReason,
    ScrapedListing,
    ScrapeFailure,
    ScrapeOutcome,
)
from braunprices.domain.model.store import Store
from braunprices.domain.value_objects.currency import Currency
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.scraping.http_client import CollectionHttpClient, FetchedPage
from braunprices.infrastructure.scraping.json_ld import ProductMarkup, extract_product

logger = structlog.get_logger(__name__)

WORTEN_SLUG = StoreSlug("worten")

# Seletores derivados de tests/fixtures/html/worten-produto-*-2026-08-15.html.gz.
_PRICE_META = 'meta[itemprop="price"]'
_CURRENCY_META = 'meta[itemprop="priceCurrency"]'
_THIRD_PARTY_OFFER_CONTAINER = "product-other-offers"
_PRODUCT_NAME = "h1"


class WortenScraper:
    """Observa preços em www.worten.pt."""

    def __init__(self, store: Store, http_client: CollectionHttpClient) -> None:
        if store.slug != WORTEN_SLUG:
            message = f"Este adaptador é da Worten, não de {store.slug}."
            raise ValueError(message)
        self._store = store
        self._http = http_client

    @property
    def store_slug(self) -> StoreSlug:
        """A loja que este adaptador sabe ler."""
        return WORTEN_SLUG

    def fetch(self, listing: StoreListing) -> ScrapeOutcome:
        """Observa o preço desta referência agora."""
        page = self._http.get(listing.url, self._store.rate_limit)
        if isinstance(page, ScrapeFailure):
            return page
        return self.parse(listing, page, observed_at=ObservedAt(datetime.now(UTC)))

    def parse(
        self,
        listing: StoreListing,
        page: FetchedPage,
        observed_at: ObservedAt,
    ) -> ScrapeOutcome:
        """Extrai a observação de uma página já obtida.

        Separado de :meth:`fetch` para que os testes possam correr contra fixtures de
        HTML real sem tocar na rede.
        """
        markup = extract_product(page.html)
        source = ExtractionSource.JSON_LD

        if isinstance(markup, ScrapeFailure):
            logger.info(
                "recolha.fallback_para_html",
                loja=WORTEN_SLUG.value,
                url=listing.url,
                motivo=markup.reason.value,
                detalhe=markup.detail,
            )
            recovered = _extract_from_microdata(page.html)
            if isinstance(recovered, ScrapeFailure):
                return recovered
            markup = recovered
            source = ExtractionSource.HTML_FALLBACK

        observation = PriceObservation(
            listing_id=listing.listing_id,
            store_slug=WORTEN_SLUG,
            observed_at=observed_at,
            price=markup.price,
            availability=markup.availability,
            source_url=page.url,
            raw_hash=content_hash(page.html),
        )
        return ScrapedListing(
            observation=observation,
            product_name=markup.name,
            ean=markup.ean,
            source=source,
        )


def content_hash(html: str) -> str:
    """Impressão digital do conteúdo de onde o preço foi lido.

    Serve para verificar mais tarde de que exato conteúdo saiu um número, e para
    detetar que uma página não mudou entre passagens.
    """
    return f"sha256:{hashlib.sha256(html.encode('utf-8')).hexdigest()}"


def _extract_from_microdata(html: str) -> ProductMarkup | ScrapeFailure:
    """Recurso: lê os microdados quando o JSON-LD não serve.

    Recusa deliberadamente quando há mais do que um preço próprio distinto. Com três
    elementos de preço na página, adivinhar qual é o da loja trocaria uma falha visível
    por um número errado no histórico — e o número errado nunca mais sai de lá.
    """
    tree = HTMLParser(html)
    own_prices = {
        (node.attributes.get("content") or "").strip()
        for node in tree.css(_PRICE_META)
        if node.attributes.get("content") and not _is_inside_third_party_offer(node)
    }

    if not own_prices:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_MISSING,
            detail="Sem JSON-LD e sem microdados de preço próprios na página.",
        )
    if len(own_prices) > 1:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_AMBIGUOUS,
            detail=(
                f"A página declara {len(own_prices)} preços próprios distintos "
                f"({sorted(own_prices)}) e não há como saber qual é o praticado. "
                f"Registar um deles ao acaso seria pior do que não registar nada."
            ),
        )

    currency_codes = {
        (node.attributes.get("content") or "").strip()
        for node in tree.css(_CURRENCY_META)
        if node.attributes.get("content")
    }
    if len(currency_codes) > 1:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_AMBIGUOUS,
            detail=f"A página declara mais do que uma moeda: {sorted(currency_codes)}.",
        )

    try:
        currency = Currency.of(next(iter(currency_codes), "EUR"))
        price = Money.of(next(iter(own_prices)), currency)
    except (DomainError, ArithmeticError, ValueError) as error:
        return ScrapeFailure(
            reason=FailureReason.PRICE_UNREADABLE,
            detail=f"Preço dos microdados não é utilizável: {error}",
        )

    name_node = tree.css_first(_PRODUCT_NAME)
    name = name_node.text(strip=True) if name_node is not None else ""
    if not name:
        return ScrapeFailure(
            reason=FailureReason.MARKUP_INVALID,
            detail="Sem JSON-LD e sem nome de produto legível na página.",
        )

    # Os microdados desta loja não declaram disponibilidade nem código de barras. UNKNOWN
    # é a resposta honesta: a observação fica registada, mas não conta como preço
    # praticado no cálculo da janela legal, porque não sabemos se era comprável.
    return ProductMarkup(
        name=name,
        price=price,
        availability=_availability_from_microdata(tree),
        ean=_ean_from_microdata(tree),
        sku=None,
    )


def _is_inside_third_party_offer(node: object) -> bool:
    """Indica se este elemento pertence ao bloco de ofertas de vendedores terceiros."""
    current = getattr(node, "parent", None)
    while current is not None:
        classes = current.attributes.get("class") or ""
        if _THIRD_PARTY_OFFER_CONTAINER in classes:
            return True
        current = current.parent
    return False


def _availability_from_microdata(tree: HTMLParser) -> Availability:
    node = tree.css_first('link[itemprop="availability"], meta[itemprop="availability"]')
    if node is None:
        return Availability.UNKNOWN
    raw = node.attributes.get("href") or node.attributes.get("content") or ""
    term = raw.rsplit("/", 1)[-1].strip().lower()
    return {"instock": Availability.IN_STOCK, "outofstock": Availability.OUT_OF_STOCK}.get(
        term, Availability.UNKNOWN
    )


def _ean_from_microdata(tree: HTMLParser) -> EAN | None:
    node = tree.css_first('meta[itemprop="gtin13"], meta[itemprop="gtin"]')
    if node is None:
        return None
    raw = node.attributes.get("content")
    if not raw:
        return None
    try:
        return EAN(raw)
    except DomainError:
        return None
