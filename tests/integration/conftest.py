"""Infraestrutura real para os testes de integração.

Postgres a sério, num container, com as migrações do Alembic aplicadas — não um
esquema criado por ``metadata.create_all``. A diferença importa: o que corre em
produção são as migrações, e um teste que salte esse passo deixa de cobrir
precisamente o ficheiro mais fácil de escrever errado.

Cada teste corre dentro de uma transação que é revertida no fim, o que os mantém
isolados sem recriar o container por teste.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from testcontainers.community.postgres import PostgresContainer

from braunprices.infrastructure.persistence.engine import build_engine

PROJECT_ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Levanta um PostgreSQL 16 e devolve o URL de ligação."""
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    """Aplica as migrações e devolve o engine sobre a base de dados já migrada."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    previous = os.environ.get("BRAUNPRICES_DATABASE_URL")
    os.environ["BRAUNPRICES_DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
        engine = build_engine(database_url)
        yield engine
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("BRAUNPRICES_DATABASE_URL", None)
        else:
            os.environ["BRAUNPRICES_DATABASE_URL"] = previous


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
