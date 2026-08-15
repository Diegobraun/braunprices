"""O histórico é append-only na base de dados, não apenas no código.

Uma invariante que existe só na camada de aplicação sobrevive até à primeira sessão de
``psql``. Estes testes atacam a tabela diretamente, por fora dos repositórios, que é
como o erro aconteceria na vida real.
"""

import pytest
from sqlalchemy import Connection, text

from braunprices.infrastructure.persistence.repositories import (
    SqlPriceObservationRepository,
    SqlProductRepository,
    SqlStoreRepository,
)
from tests.integration.factories import a_listing, a_product, a_store, an_observation


@pytest.fixture
def a_stored_observation(connection: Connection) -> None:
    """Deixa uma observação gravada, pronta a ser atacada."""
    stores = SqlStoreRepository(connection)
    products = SqlProductRepository(connection)
    observations = SqlPriceObservationRepository(connection)
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all([an_observation(listing, day="2026-07-01", price="59.99")])


@pytest.mark.usefixtures("a_stored_observation")
def test_updating_a_price_is_refused_by_the_database(connection: Connection) -> None:
    with pytest.raises(Exception, match="append-only"):
        connection.execute(text("UPDATE price_observations SET price_amount = 1"))


@pytest.mark.usefixtures("a_stored_observation")
def test_updating_any_column_at_all_is_refused(connection: Connection) -> None:
    # Não é só o preço: mexer na proveniência ou no carimbo temporal reescreveria o
    # facto tão bem como mexer no valor.
    with pytest.raises(Exception, match="append-only"):
        connection.execute(text("UPDATE price_observations SET source_url = 'https://x.pt'"))


@pytest.mark.usefixtures("a_stored_observation")
def test_deleting_an_observation_is_refused(connection: Connection) -> None:
    with pytest.raises(Exception, match="append-only"):
        connection.execute(text("DELETE FROM price_observations"))


@pytest.mark.usefixtures("a_stored_observation")
def test_the_refusal_names_the_correct_way_to_fix_a_wrong_observation(
    connection: Connection,
) -> None:
    # A mensagem faz parte do desenho: quem bate nesta parede tem de saber que a
    # correção é registar outro facto, não sobrescrever o original.
    with pytest.raises(Exception, match="registando outro facto"):
        connection.execute(text("UPDATE price_observations SET price_amount = 1"))


@pytest.mark.usefixtures("a_stored_observation")
def test_deleting_a_listing_that_has_history_is_refused(connection: Connection) -> None:
    # Apagar a referência apagaria o histórico em cascata por uma porta lateral.
    with pytest.raises(Exception, match="fk_price_observations_listing_id_store_listings"):
        connection.execute(text("DELETE FROM store_listings"))


def test_the_repository_offers_no_way_to_mutate_history() -> None:
    # A ausência é a interface: se um método destes existisse, alguém acabaria por o
    # chamar com uma boa razão.
    surface = dir(SqlPriceObservationRepository)
    assert not [name for name in surface if name in {"update", "delete", "remove", "save"}]
