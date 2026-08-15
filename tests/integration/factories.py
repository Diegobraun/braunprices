"""Construtores de entidades para os testes de integração."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import RateLimitPolicy, Store
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug

VALID_EAN = EAN("4006381333931")
OTHER_EAN = EAN("5449000000996")


def a_store(slug: str = "loja-exemplo", **overrides: object) -> Store:
    """Loja com política conservadora, pronta a inserir."""
    values: dict[str, object] = {
        "slug": StoreSlug(slug),
        "name": f"Loja {slug}",
        "base_domain": f"{slug}.pt",
        "rate_limit": RateLimitPolicy(),
    }
    values.update(overrides)
    return Store(**values)  # type: ignore[arg-type]


def a_listing(
    store: str = "loja-exemplo",
    external_id: str = "12345",
    listing_id: UUID | None = None,
    *,
    is_active: bool = True,
) -> StoreListing:
    """Referência de produto dentro de uma loja."""
    return StoreListing(
        listing_id=listing_id or uuid4(),
        store_slug=StoreSlug(store),
        external_id=external_id,
        url=f"https://{store}.pt/p/{external_id}",
        is_active=is_active,
    )


def a_product(
    *,
    ean: EAN | None = VALID_EAN,
    name: str = "Máquina de café",
    listings: list[StoreListing] | None = None,
    product_id: UUID | None = None,
) -> Product:
    """Produto com identidade própria e as referências indicadas."""
    return Product(
        product_id=product_id or uuid4(),
        canonical_name=name,
        ean=ean,
        listings=listings if listings is not None else [],
    )


def an_observation(
    listing: StoreListing,
    *,
    day: str = "2026-07-01",
    hour: int = 9,
    price: str = "59.99",
    availability: Availability = Availability.IN_STOCK,
) -> PriceObservation:
    """Observação de preço num dia de Lisboa."""
    year, month, day_of_month = (int(part) for part in day.split("-"))
    return PriceObservation(
        listing_id=listing.listing_id,
        store_slug=listing.store_slug,
        observed_at=ObservedAt.from_lisbon(datetime(year, month, day_of_month, hour, 0)),  # noqa: DTZ001
        price=Money.of(Decimal(price)),
        availability=availability,
        source_url=listing.url,
        raw_hash=f"sha256:{day}-{hour}-{price}",
    )
