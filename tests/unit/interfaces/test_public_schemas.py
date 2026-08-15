"""As formas que a API devolve, sem rede nem base de dados.

O que se verifica aqui é o que um terceiro vê: dinheiro em texto decimal, linguagem
descritiva, e nenhum campo que qualifique a conduta de uma loja.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.store import RateLimitPolicy, Store
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.interfaces.api.public import schemas
from braunprices.interfaces.api.public.schemas import MoneyOut, ObservationOut, StoreOut
from tests.integration.factories import a_listing


def an_observation(
    price: str, availability: Availability = Availability.IN_STOCK
) -> PriceObservation:
    listing = a_listing()
    return PriceObservation(
        listing_id=listing.listing_id,
        store_slug=listing.store_slug,
        observed_at=ObservedAt(datetime(2026, 7, 4, 23, 30, tzinfo=UTC)),
        price=Money.of(Decimal(price)),
        availability=availability,
        source_url=listing.url,
        raw_hash="sha256:abc",
    )


@pytest.mark.parametrize("amount", ["59.99", "59.90", "0.05", "1234.00"])
def test_money_keeps_its_scale_as_text(amount: str) -> None:
    # `59.9` e `59.90` são o mesmo número e não são o mesmo preço observado.
    assert MoneyOut.of(Money.of(Decimal(amount))).montante == amount


def test_money_is_never_serialized_as_a_number() -> None:
    payload = MoneyOut.of(Money.of(Decimal("99.67"))).model_dump_json()
    assert payload == '{"montante":"99.67","moeda":"EUR"}'


def test_an_observation_carries_the_day_in_lisbon_and_not_in_utc() -> None:
    # 23:30 UTC de 4 de julho é já dia 5 em Lisboa. A fronteira do dia é a de cá,
    # porque é a de cá que a lei conta.
    published = ObservationOut.of(an_observation("59.99"))
    assert published.observado_em == datetime(2026, 7, 4, 23, 30, tzinfo=UTC)
    assert published.dia.isoformat() == "2026-07-05"


def test_an_observation_says_whether_it_counts_towards_the_legal_window() -> None:
    assert ObservationOut.of(an_observation("59.99")).conta_como_preco_praticado is True
    esgotado = an_observation("59.99", Availability.OUT_OF_STOCK)
    assert ObservationOut.of(esgotado).conta_como_preco_praticado is False


def test_an_observation_publishes_where_it_came_from() -> None:
    # Sem proveniência, o número não é verificável por quem o lê — e este sistema
    # publica afirmações sobre empresas identificadas.
    published = ObservationOut.of(an_observation("59.99"))
    assert published.url.startswith("https://")
    assert published.impressao_do_conteudo == "sha256:abc"


def test_a_store_publishes_the_pace_it_is_visited_at() -> None:
    store = Store(
        slug=StoreSlug("worten"),
        name="Worten",
        base_domain="www.worten.pt",
        rate_limit=RateLimitPolicy(requests_per_second=0.25),
    )
    assert StoreOut.of(store).pedidos_por_segundo == 0.25


def test_no_published_field_qualifies_anyone_s_conduct() -> None:
    # A linguagem é descritiva em todo o lado, e isto é a rede de segurança: um campo
    # chamado `infracao` ou `ilegal` nasceria aqui e ninguém daria por ele.
    evaluative = ("infra", "ilegal", "fraude", "abuso", "irregular", "incumpr", "suspeit")
    published = [
        name
        for model in vars(schemas).values()
        if isinstance(model, type) and hasattr(model, "model_fields")
        for name in model.model_fields
    ]
    assert published
    assert not [name for name in published if any(word in name.lower() for word in evaluative)]
