"""Unidade de trabalho sobre uma ligação do SQLAlchemy."""

from types import TracebackType
from typing import Self

from sqlalchemy import Connection, Engine

from braunprices.infrastructure.persistence.collection_reports import (
    SqlCollectionReportRepository,
)
from braunprices.infrastructure.persistence.repositories import (
    SqlPriceObservationRepository,
    SqlProductRepository,
    SqlStoreRepository,
)


class SqlUnitOfWork:
    """Abre uma transação e expõe os repositórios que lhe pertencem.

    Sair do bloco sem ``commit`` reverte tudo. É o contrário do que uma ligação com
    *autocommit* faria, e é deliberado: numa passagem de recolha, gravar metade de um
    lote seria pior do que não gravar nada.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._committed = False

    def __enter__(self) -> Self:
        """Abre a ligação e começa a transação."""
        self._connection = self._engine.connect()
        self._connection.begin()
        self._committed = False
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Reverte se não houve commit, e fecha sempre a ligação."""
        if self._connection is None:  # pragma: no cover - só se __enter__ não correu
            return
        try:
            if not self._committed:
                self._connection.rollback()
        finally:
            self._connection.close()
            self._connection = None

    def commit(self) -> None:
        """Confirma o trabalho feito até aqui."""
        self._active.commit()
        self._committed = True

    @property
    def _active(self) -> Connection:
        if self._connection is None:
            message = "A unidade de trabalho tem de ser usada dentro de um bloco `with`."
            raise RuntimeError(message)
        return self._connection

    @property
    def stores(self) -> SqlStoreRepository:
        """Lojas configuradas."""
        return SqlStoreRepository(self._active)

    @property
    def products(self) -> SqlProductRepository:
        """Produtos e as suas referências em lojas."""
        return SqlProductRepository(self._active)

    @property
    def observations(self) -> SqlPriceObservationRepository:
        """Histórico de observações, append-only."""
        return SqlPriceObservationRepository(self._active)

    @property
    def reports(self) -> SqlCollectionReportRepository:
        """Relatos das passagens de recolha."""
        return SqlCollectionReportRepository(self._active)
