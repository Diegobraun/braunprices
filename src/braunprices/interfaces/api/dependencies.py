"""As peças que os endpoints recebem.

O container é montado uma vez no arranque e guardado no estado da aplicação, e não a
cada pedido: cada montagem cria um engine com pool próprio, e um pool por pedido é a
forma mais rápida de esgotar as ligações de um Postgres.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from braunprices.application.queries.catalogue import GetProduct, ListStores
from braunprices.application.queries.price_history import GetPriceHistory
from braunprices.application.queries.reference_price import GetReferencePrice
from braunprices.domain.ports.unit_of_work import UnitOfWork
from braunprices.infrastructure.composition import Container


def container_of(request: Request) -> Container:
    """Devolve o container montado no arranque."""
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(container_of)]


def unit_of_work_of(container: ContainerDep) -> Callable[[], UnitOfWork]:
    """Devolve a fábrica de unidades de trabalho."""
    return container.unit_of_work


UnitOfWorkFactoryDep = Annotated[Callable[[], UnitOfWork], Depends(unit_of_work_of)]


def price_history_query(unit_of_work: UnitOfWorkFactoryDep) -> GetPriceHistory:
    """Monta a consulta de histórico."""
    return GetPriceHistory(unit_of_work=unit_of_work)


def reference_price_query(unit_of_work: UnitOfWorkFactoryDep) -> GetReferencePrice:
    """Monta a consulta do preço de referência."""
    return GetReferencePrice(unit_of_work=unit_of_work)


def stores_query(unit_of_work: UnitOfWorkFactoryDep) -> ListStores:
    """Monta a consulta de lojas."""
    return ListStores(unit_of_work=unit_of_work)


def product_query(unit_of_work: UnitOfWorkFactoryDep) -> GetProduct:
    """Monta a consulta de produtos."""
    return GetProduct(unit_of_work=unit_of_work)


PriceHistoryDep = Annotated[GetPriceHistory, Depends(price_history_query)]
ReferencePriceDep = Annotated[GetReferencePrice, Depends(reference_price_query)]
StoresDep = Annotated[ListStores, Depends(stores_query)]
ProductDep = Annotated[GetProduct, Depends(product_query)]
