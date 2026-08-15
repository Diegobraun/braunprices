"""Construtores de dados para os testes de domínio.

São construtores, não mocks: devolvem entidades reais do domínio. No domínio não há
I/O nenhum, logo não há nada que valha a pena substituir por um duplo — se aqui
surgisse a necessidade de um mock, seria sinal de que o desenho está errado.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug

LISTING_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_LISTING_ID = UUID("22222222-2222-4222-8222-222222222222")
STORE = StoreSlug("loja-exemplo")
SOURCE_URL = "https://loja-exemplo.pt/p/12345"


def observation(  # noqa: PLR0913 - cada argumento é um eixo que algum teste varia
    *,
    day: str,
    price: str | Decimal,
    hour: int = 9,
    availability: Availability = Availability.IN_STOCK,
    listing_id: UUID = LISTING_ID,
    store: StoreSlug = STORE,
    currency_amount: Money | None = None,
) -> PriceObservation:
    """Cria uma observação num dia de Lisboa, com o mínimo de cerimónia.

    ``day`` é uma data ISO e ``hour`` a hora local, para que os testes de fronteira
    possam escrever explicitamente a hora que interessa.
    """
    year, month, date_of_month = (int(part) for part in day.split("-"))
    return PriceObservation(
        listing_id=listing_id,
        store_slug=store,
        observed_at=ObservedAt.from_lisbon(datetime(year, month, date_of_month, hour, 0)),  # noqa: DTZ001
        price=currency_amount if currency_amount is not None else Money.of(Decimal(str(price))),
        availability=availability,
        source_url=SOURCE_URL,
        raw_hash=f"sha256:{day}-{price}",
    )


@pytest.fixture
def daily_series() -> list[PriceObservation]:
    """Série estável: o mesmo preço todos os dias de uma janela completa."""
    return [observation(day=f"2026-06-{day:02d}", price="59.99") for day in range(12, 31)]
