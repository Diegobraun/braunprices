"""Ligações à base de dados real, para os testes que precisam de uma transação.

Cada teste corre dentro de uma transação revertida no fim, o que os mantém isolados sem
recriar o container por teste.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text


@pytest.fixture
def connection(migrated_engine: Engine) -> Iterator[Connection]:
    """Ligação dentro de uma transação revertida no fim do teste."""
    with migrated_engine.connect() as raw_connection:
        transaction = raw_connection.begin()
        try:
            yield raw_connection
        finally:
            transaction.rollback()


@pytest.fixture
def autonomous_connection(migrated_engine: Engine) -> Iterator[Connection]:
    """Ligação sem transação envolvente, para testes que precisam de commit real.

    Serve os casos em que o próprio commit é o que está sob teste — por exemplo
    verificar que o trigger de append-only trava um UPDATE mesmo fora da aplicação.
    A limpeza é explícita porque não há rollback a apanhá-la.
    """
    with migrated_engine.connect() as raw_connection:
        yield raw_connection
        raw_connection.rollback()
        with migrated_engine.begin() as cleanup:
            cleanup.execute(
                text(
                    "TRUNCATE price_observations, store_listings, products, stores "
                    "RESTART IDENTITY CASCADE"
                )
            )
