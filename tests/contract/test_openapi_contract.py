"""O contrato publicado é verificado contra o serviço a sério.

Um OpenAPI escrito à mão diverge do código na semana seguinte, e ninguém dá por isso
até um cliente rebentar. Aqui o schemathesis lê o contrato que o próprio serviço
publica, gera pedidos a partir dele — incluindo os que ninguém escreveria à mão — e
verifica que as respostas cabem no que foi prometido.

Apanha uma classe de erros que os testes escritos à mão não apanham: o campo que o
contrato diz ser obrigatório e vem a nulo, o 500 onde devia estar um 400, o código de
estado que ninguém documentou.
"""

from collections.abc import Iterator
from datetime import datetime

import pytest
import schemathesis
from fastapi import FastAPI
from hypothesis import HealthCheck, settings
from schemathesis.config import SchemathesisConfig
from sqlalchemy import Engine, text

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.infrastructure import composition
from braunprices.infrastructure.config import Settings
from braunprices.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from braunprices.interfaces.api.app import create_app
from tests.integration.factories import a_listing, a_product, a_store

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded_app(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Aplicação com algum histórico, para que as rotas tenham o que devolver."""
    listing = a_listing("loja-exemplo", "5513302")
    with SqlUnitOfWork(migrated_engine) as work:
        work.stores.add(a_store())
        work.products.add(a_product(name="Tinteiro HP 971", listings=[listing]))
        work.observations.add_all(
            [
                PriceObservation(
                    listing_id=listing.listing_id,
                    store_slug=listing.store_slug,
                    observed_at=ObservedAt.from_lisbon(datetime(2026, 7, day, 9)),  # noqa: DTZ001
                    price=Money.of(f"{100 - day}.50"),
                    availability=Availability.IN_STOCK,
                    source_url=listing.url,
                    raw_hash=f"sha256:contrato-{day}",
                )
                for day in range(1, 6)
            ]
        )
        work.commit()

    monkeypatch.setattr(composition, "build_engine", lambda _url: migrated_engine)
    yield create_app(Settings())

    with migrated_engine.begin() as cleanup:
        cleanup.execute(
            text(
                "TRUNCATE collection_failures, collection_runs, price_observations, "
                "store_listings, products, stores RESTART IDENTITY CASCADE"
            )
        )


# Um pedido pode respeitar o contrato e ainda assim ser recusado: o esquema diz que
# `ean` é texto, mas nem todo o texto é um EAN — o dígito de controlo não cabe num tipo,
# e o cursor é opaco por desenho. Recusar esses casos com 400 é o comportamento certo, e
# é por isso que estes códigos entram na lista do que conta como resposta legítima. O
# que continua a ser apanhado é o essencial: nenhum 5xx, e cada resposta a caber no
# esquema que o contrato promete.
CONTRACT_CONFIG = SchemathesisConfig.from_dict(
    {"checks": {"positive_data_acceptance": {"expected-statuses": [200, 400, 404, 422]}}}
)


@pytest.fixture
def api_schema(seeded_app: FastAPI) -> schemathesis.BaseSchema:
    """O contrato tal como o serviço o publica, sobre a aplicação em memória."""
    return schemathesis.openapi.from_asgi("/openapi.json", seeded_app, config=CONTRACT_CONFIG)


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@settings(
    max_examples=25,
    deadline=None,
    # A base de dados é partilhada por toda a sessão e é lenta a arrancar; a saúde que
    # o hypothesis mede aqui seria a do container, não a do código.
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
def test_every_documented_operation_keeps_its_promise(case: schemathesis.Case) -> None:  # type: ignore[type-arg]
    """Chama a operação com dados gerados do contrato e valida a resposta."""
    case.call_and_validate()
