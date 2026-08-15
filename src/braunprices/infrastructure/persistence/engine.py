"""Criação do engine e a definição de unidade de trabalho."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, create_engine


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Cria o engine para a base de dados indicada.

    ``pool_pre_ping`` está ligado porque a recolha diária corre em passagens longas e
    espaçadas: sem ele, a primeira consulta depois de horas de inatividade encontra
    uma ligação que o servidor já fechou.
    """
    return create_engine(database_url, echo=echo, pool_pre_ping=True, future=True)


@contextmanager
def unit_of_work(engine: Engine) -> Iterator[Connection]:
    """Abre uma ligação com transação, com commit no fim e rollback em caso de erro.

    Quem decide o que é uma unidade de trabalho é o caso de uso. Os repositórios
    recebem a ligação e não gerem transações — se cada um fizesse o seu commit, uma
    passagem de recolha deixaria de ser atómica sem que nada o dissesse.
    """
    with engine.begin() as connection:
        yield connection
