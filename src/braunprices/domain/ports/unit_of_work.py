"""A unidade de trabalho, definida pelo domínio.

Quem decide o que é uma transação é o caso de uso, não o armazenamento. Este porto é o
que lhe permite decidir sem saber que existe SQLAlchemy do outro lado.
"""

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from braunprices.domain.ports.repositories import (
    PriceObservationRepository,
    ProductRepository,
    StoreRepository,
)


class UnitOfWork(Protocol):
    """Uma transação com os repositórios que lhe pertencem.

    Sair do bloco sem chamar ``commit`` reverte tudo. É o contrário do que uma sessão
    com *autocommit* faria, e é deliberado: numa passagem de recolha, gravar metade
    seria pior do que não gravar nada.
    """

    @property
    def stores(self) -> StoreRepository:
        """Lojas configuradas."""
        ...

    @property
    def products(self) -> ProductRepository:
        """Produtos e as suas referências em lojas."""
        ...

    @property
    def observations(self) -> PriceObservationRepository:
        """Histórico de observações, append-only."""
        ...

    def commit(self) -> None:
        """Confirma o trabalho feito até aqui."""
        ...

    def __enter__(self) -> Self:
        """Abre a transação."""
        ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Fecha a transação, revertendo se não houve commit."""
        ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
