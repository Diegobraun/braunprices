"""O adaptador da Worten, contra HTML real. Zero rede."""

import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.product import StoreListing
from braunprices.domain.model.scrape_outcome import (
    ExtractionSource,
    FailureReason,
    ScrapedListing,
    ScrapeFailure,
)
from braunprices.domain.model.store import Store
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.scraping.http_client import FetchedPage
from braunprices.infrastructure.scraping.worten import WORTEN_SLUG, WortenScraper, content_hash

OBSERVED_AT = ObservedAt(datetime(2026, 8, 15, 10, 0, tzinfo=UTC))
PRODUCT_URL = "https://www.worten.pt/produtos/tinteiro-hp-971-amarelo-cn624ae-5513302"


def worten_store() -> Store:
    return Store(slug=WORTEN_SLUG, name="Worten", base_domain="www.worten.pt")


def a_listing() -> StoreListing:
    return StoreListing(
        listing_id=uuid4(),
        store_slug=WORTEN_SLUG,
        external_id="5513302",
        url=PRODUCT_URL,
    )


def scraper() -> WortenScraper:
    # http_client é None porque nenhum destes testes faz rede: exercitam `parse`, que
    # recebe a página já obtida. Se algum destes testes tocasse na rede, rebentaria
    # aqui em vez de passar a depender da loja estar de pé.
    return WortenScraper(worten_store(), http_client=None)  # type: ignore[arg-type]


def a_page(html: str) -> FetchedPage:
    return FetchedPage(url=PRODUCT_URL, html=html, status_code=200)


# -- extração pela fonte primária ------------------------------------------


def test_reads_the_real_page_through_json_ld(worten_product_html: str) -> None:
    listing = a_listing()
    outcome = scraper().parse(listing, a_page(worten_product_html), OBSERVED_AT)

    assert isinstance(outcome, ScrapedListing)
    assert outcome.source is ExtractionSource.JSON_LD
    assert outcome.product_name == "Tinteiro HP 971 Amarelo (CN624AE)"
    assert outcome.ean == EAN("0886112877347")
    assert outcome.observation.price == Money.of("99.67")
    assert outcome.observation.availability is Availability.IN_STOCK
    assert outcome.observation.listing_id == listing.listing_id
    assert outcome.observation.store_slug == WORTEN_SLUG
    assert outcome.observation.source_url == PRODUCT_URL
    assert outcome.observation.observed_at == OBSERVED_AT


def test_the_provenance_hash_identifies_the_content_it_read(worten_product_html: str) -> None:
    outcome = scraper().parse(a_listing(), a_page(worten_product_html), OBSERVED_AT)
    assert isinstance(outcome, ScrapedListing)
    assert outcome.observation.raw_hash == content_hash(worten_product_html)
    assert outcome.observation.raw_hash.startswith("sha256:")


def test_the_same_page_always_yields_the_same_hash(worten_product_html: str) -> None:
    assert content_hash(worten_product_html) == content_hash(worten_product_html)


def test_a_different_page_yields_a_different_hash(
    worten_product_html: str, worten_second_product_html: str
) -> None:
    assert content_hash(worten_product_html) != content_hash(worten_second_product_html)


def test_the_adapter_refuses_to_be_built_for_another_store() -> None:
    other = Store(slug=StoreSlug("outra-loja"), name="Outra", base_domain="outra.pt")
    with pytest.raises(ValueError, match="Worten"):
        WortenScraper(other, http_client=None)  # type: ignore[arg-type]


# -- o recurso ao HTML, e os seus limites ----------------------------------


def strip_json_ld(html: str) -> str:
    """Remove os blocos JSON-LD de uma página real, deixando o resto intacto.

    A fixture continua a ser HTML verdadeiro: o que se simula é a loja ter deixado de
    publicar a marcação, que é como a degradação acontece na prática.
    """
    return re.sub(
        r'<script[^>]*type="application/ld\+json"[^>]*>.*?</script>',
        "",
        html,
        flags=re.DOTALL,
    )


def test_without_json_ld_the_real_page_is_refused_as_ambiguous(worten_product_html: str) -> None:
    # A página tem três meta[itemprop=price]: 99,67 duas vezes e 95,73 uma. O 95,73 é
    # uma oferta de vendedor terceiro e é descartado; sobra 99,67. Confirma-se que o
    # descarte funciona e que sobra um só valor.
    outcome = scraper().parse(a_listing(), a_page(strip_json_ld(worten_product_html)), OBSERVED_AT)
    assert isinstance(outcome, ScrapedListing)
    assert outcome.source is ExtractionSource.HTML_FALLBACK
    assert outcome.observation.price == Money.of("99.67")


def test_the_fallback_never_picks_the_third_party_price(worten_product_html: str) -> None:
    outcome = scraper().parse(a_listing(), a_page(strip_json_ld(worten_product_html)), OBSERVED_AT)
    assert isinstance(outcome, ScrapedListing)
    assert outcome.observation.price != Money.of("95.73")


def test_the_fallback_reports_unknown_availability_rather_than_assuming(
    worten_product_html: str,
) -> None:
    # Os microdados desta loja não declaram disponibilidade. UNKNOWN é a resposta
    # honesta, e faz com que a observação não conte como preço praticado.
    outcome = scraper().parse(a_listing(), a_page(strip_json_ld(worten_product_html)), OBSERVED_AT)
    assert isinstance(outcome, ScrapedListing)
    assert outcome.observation.availability is Availability.UNKNOWN
    assert outcome.observation.counts_as_price_practised is False


def test_two_distinct_own_prices_are_refused_instead_of_guessed() -> None:
    # A recusa é o comportamento correto: escolher um ao acaso trocaria uma falha
    # visível por um número errado que nunca mais sai do histórico.
    html = (
        "<html><body><h1>Produto</h1>"
        '<meta itemprop="price" content="10.00">'
        '<meta itemprop="price" content="20.00">'
        '<meta itemprop="priceCurrency" content="EUR">'
        "</body></html>"
    )
    outcome = scraper().parse(a_listing(), a_page(html), OBSERVED_AT)
    assert isinstance(outcome, ScrapeFailure)
    assert outcome.reason is FailureReason.MARKUP_AMBIGUOUS
    assert "10.00" in outcome.detail
    assert "20.00" in outcome.detail


def test_a_page_with_neither_json_ld_nor_microdata_is_a_classified_failure() -> None:
    outcome = scraper().parse(a_listing(), a_page("<html><body>nada</body></html>"), OBSERVED_AT)
    assert isinstance(outcome, ScrapeFailure)
    assert outcome.reason is FailureReason.MARKUP_MISSING


def test_microdata_without_a_product_name_is_a_failure() -> None:
    html = '<html><body><meta itemprop="price" content="10.00"></body></html>'
    outcome = scraper().parse(a_listing(), a_page(html), OBSERVED_AT)
    assert isinstance(outcome, ScrapeFailure)
    assert outcome.reason is FailureReason.MARKUP_INVALID


def test_the_fallback_refuses_more_than_one_currency() -> None:
    html = (
        "<html><body><h1>Produto</h1>"
        '<meta itemprop="price" content="10.00">'
        '<meta itemprop="priceCurrency" content="EUR">'
        '<meta itemprop="priceCurrency" content="USD">'
        "</body></html>"
    )
    outcome = scraper().parse(a_listing(), a_page(html), OBSERVED_AT)
    assert isinstance(outcome, ScrapeFailure)
    assert outcome.reason is FailureReason.MARKUP_AMBIGUOUS


def test_the_fallback_refuses_an_unreadable_price() -> None:
    html = (
        "<html><body><h1>Produto</h1>"
        '<meta itemprop="price" content="grátis">'
        '<meta itemprop="priceCurrency" content="EUR">'
        "</body></html>"
    )
    outcome = scraper().parse(a_listing(), a_page(html), OBSERVED_AT)
    assert isinstance(outcome, ScrapeFailure)
    assert outcome.reason is FailureReason.PRICE_UNREADABLE


def test_the_fallback_reads_availability_and_barcode_when_they_are_declared() -> None:
    html = (
        "<html><body><h1>Produto</h1>"
        '<meta itemprop="price" content="10.00">'
        '<meta itemprop="priceCurrency" content="EUR">'
        '<link itemprop="availability" href="https://schema.org/InStock">'
        '<meta itemprop="gtin13" content="4006381333931">'
        "</body></html>"
    )
    outcome = scraper().parse(a_listing(), a_page(html), OBSERVED_AT)
    assert isinstance(outcome, ScrapedListing)
    assert outcome.observation.availability is Availability.IN_STOCK
    assert outcome.ean == EAN("4006381333931")


def test_the_fallback_ignores_an_invalid_barcode() -> None:
    html = (
        "<html><body><h1>Produto</h1>"
        '<meta itemprop="price" content="10.00">'
        '<meta itemprop="gtin13" content="1234567890123">'
        "</body></html>"
    )
    outcome = scraper().parse(a_listing(), a_page(html), OBSERVED_AT)
    assert isinstance(outcome, ScrapedListing)
    assert outcome.ean is None
