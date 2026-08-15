"""Tradução explícita entre linhas da base de dados e entidades do domínio.

Explícita de propósito. É mais código do que um mapeamento automático, e é o preço
de manter ``PriceObservation`` congelada — o ORM precisaria de escrever nos atributos
ao carregar. Ver ADR-0009.

A tradução é sempre nos dois sentidos e no mesmo ficheiro, para que um campo novo que
se acrescente a um lado e se esqueça no outro salte à vista em revisão.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import RowMapping

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import RateLimitPolicy, Store
from braunprices.domain.value_objects.currency import Currency
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug

# O tipo de linha do SQLAlchemy, e não um Mapping genérico: é o que os
# repositórios entregam de facto, e aceitar menos escondia a origem dos dados.
Row = RowMapping


# -- Store -----------------------------------------------------------------


def store_to_row(store: Store) -> dict[str, Any]:
    """Devolve os valores de uma linha de ``stores`` para esta loja."""
    return {
        "slug": store.slug.value,
        "name": store.name,
        "base_domain": store.base_domain,
        "requests_per_second": store.rate_limit.requests_per_second,
        "max_concurrency": store.rate_limit.max_concurrency,
        "timeout_seconds": store.rate_limit.timeout_seconds,
        "max_retries": store.rate_limit.max_retries,
        "backoff_base_seconds": store.rate_limit.backoff_base_seconds,
    }


def row_to_store(row: Row) -> Store:
    """Reconstrói a loja a partir de uma linha de ``stores``."""
    return Store(
        slug=StoreSlug(row["slug"]),
        name=row["name"],
        base_domain=row["base_domain"],
        rate_limit=RateLimitPolicy(
            requests_per_second=row["requests_per_second"],
            max_concurrency=row["max_concurrency"],
            timeout_seconds=row["timeout_seconds"],
            max_retries=row["max_retries"],
            backoff_base_seconds=row["backoff_base_seconds"],
        ),
    )


# -- Product e StoreListing ------------------------------------------------


def product_to_row(product: Product) -> dict[str, Any]:
    """Devolve os valores de uma linha de ``products`` para este produto."""
    return {
        "product_id": product.product_id,
        "canonical_name": product.canonical_name,
        "ean": product.ean.value if product.ean is not None else None,
    }


def row_to_product(row: Row, listings: list[StoreListing]) -> Product:
    """Reconstrói o agregado a partir da linha do produto e das suas referências."""
    return Product(
        product_id=row["product_id"],
        canonical_name=row["canonical_name"],
        ean=EAN(row["ean"]) if row["ean"] is not None else None,
        listings=listings,
    )


def listing_to_row(listing: StoreListing, product_id: UUID) -> dict[str, Any]:
    """Devolve os valores de uma linha de ``store_listings`` para esta referência."""
    return {
        "listing_id": listing.listing_id,
        "product_id": product_id,
        "store_slug": listing.store_slug.value,
        "external_id": listing.external_id,
        "url": listing.url,
        "is_active": listing.is_active,
    }


def row_to_listing(row: Row) -> StoreListing:
    """Reconstrói a referência de loja a partir de uma linha de ``store_listings``."""
    return StoreListing(
        listing_id=row["listing_id"],
        store_slug=StoreSlug(row["store_slug"]),
        external_id=row["external_id"],
        url=row["url"],
        is_active=row["is_active"],
    )


# -- PriceObservation ------------------------------------------------------


def observation_to_row(observation: PriceObservation) -> dict[str, Any]:
    """Devolve os valores de uma linha de ``price_observations`` para esta observação.

    ``observation_id`` é gerado aqui, não no domínio: uma observação é identificada
    pelo facto que descreve, e a chave técnica é assunto do armazenamento.

    ``observed_day`` é escrito a partir do domínio, e não calculado em SQL, porque
    ``AT TIME ZONE 'Europe/Lisbon'`` não é IMMUTABLE em PostgreSQL e por isso não pode
    entrar num índice nem numa coluna gerada.
    """
    return {
        "observation_id": uuid4(),
        "listing_id": observation.listing_id,
        "store_slug": observation.store_slug.value,
        "observed_at": observation.observed_at.instant,
        "observed_day": observation.local_date,
        "price_amount": observation.price.amount,
        "price_currency": observation.price.currency.code,
        "availability": observation.availability.value,
        "source_url": observation.source_url,
        "raw_hash": observation.raw_hash,
    }


def row_to_observation(row: Row) -> PriceObservation:
    """Reconstrói a observação a partir de uma linha de ``price_observations``."""
    currency = Currency.of(row["price_currency"])
    return PriceObservation(
        listing_id=row["listing_id"],
        store_slug=StoreSlug(row["store_slug"]),
        observed_at=ObservedAt(row["observed_at"]),
        # A escala vem da coluna NUMERIC(14, 4) e é mais larga do que a da moeda;
        # normalizar aqui é o que faz `59.9900` voltar a ser `59.99`, e não um
        # montante que o domínio recusaria construir.
        price=Money.rounded(row["price_amount"], currency),
        availability=Availability(row["availability"]),
        source_url=row["source_url"],
        raw_hash=row["raw_hash"],
    )
