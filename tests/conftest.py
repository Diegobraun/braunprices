"""Configuração comum à suite.

Os markers são aplicados pela pasta em que o teste vive, em vez de decorados um a um.
Um marker esquecido faria o teste escapar a ``pytest -m unit``, e um teste que não corre
é pior do que um teste que não existe: dá a impressão de cobertura sem a dar.
"""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import Reaper

from braunprices.infrastructure.persistence.engine import build_engine

_MARKER_BY_DIRECTORY = {
    "unit": "unit",
    "integration": "integration",
    "architecture": "architecture",
    "contract": "integration",
}

TESTS_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marca cada teste conforme a pasta de topo em que está."""
    for item in items:
        relative = Path(str(item.fspath)).relative_to(TESTS_ROOT)
        marker = _MARKER_BY_DIRECTORY.get(relative.parts[0])
        if marker is not None:
            item.add_marker(getattr(pytest.mark, marker))


PROJECT_ROOT = Path(__file__).parents[1]

# Tentativas de levantar o container antes de desistir. Ver `database_url`.
CONTAINER_START_ATTEMPTS = 3


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Levanta um PostgreSQL 16 e devolve o URL de ligação.

    A tentativa é repetida porque o *reaper* do testcontainers, quando arranca de novo,
    é interrogado pelo porto publicado antes de o Docker o ter publicado — e a sessão
    inteira morre com ``Port mapping ... is not available`` numa falha que nada tem a
    ver com o código sob teste. Um estranho a correr `make test` num clone limpo veria
    oitenta erros e concluiria que o projeto está partido.
    """
    container = PostgresContainer("postgres:16-alpine", driver="psycopg")
    for attempt in range(1, CONTAINER_START_ATTEMPTS + 1):
        try:
            container.start()
        except ConnectionError:
            Reaper.delete_instance()
            if attempt == CONTAINER_START_ATTEMPTS:
                raise
            time.sleep(1)
        else:
            break
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


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
