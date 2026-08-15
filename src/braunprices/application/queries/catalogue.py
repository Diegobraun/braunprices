"""O que existe no sistema: lojas registadas e produtos observados."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import Store
from braunprices.domain.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from braunprices.domain.value_objects.ean import EAN


@dataclass(frozen=True, slots=True)
class ListStores:
    """Lojas de que se recolhe, com a política de ritmo declarada.

    A política é pública de propósito: quem é responsável por um dos sites consegue ver
    a que ritmo está a ser visitado sem ter de perguntar a ninguém.
    """

    unit_of_work: UnitOfWorkFactory

    def __call__(self) -> Sequence[Store]:
        """Devolve as lojas registadas, por slug."""
        with self.unit_of_work() as work:
            return work.stores.list_all()


@dataclass(frozen=True, slots=True)
class ObservedListing:
    """Uma referência de loja com a última observação conhecida."""

    listing: StoreListing
    store: Store
    latest: PriceObservation | None


@dataclass(frozen=True, slots=True)
class ProductView:
    """Um produto e o estado atual de cada referência que o representa."""

    product: Product
    listings: Sequence[ObservedListing]


@dataclass(frozen=True, slots=True)
class GetProduct:
    """Devolve um produto, pelo seu identificador ou pelo EAN."""

    unit_of_work: UnitOfWorkFactory

    def by_id(self, product_id: UUID) -> ProductView | None:
        """Devolve o produto com este identificador, ou ``None``."""
        with self.unit_of_work() as work:
            return self._view(work.products.get(product_id), work)

    def by_ean(self, ean: EAN) -> ProductView | None:
        """Devolve o produto com este EAN, ou ``None``.

        É a chave de casamento entre lojas: o mesmo EAN em duas lojas é o mesmo
        produto, e é isso que torna os dois históricos comparáveis.
        """
        with self.unit_of_work() as work:
            return self._view(work.products.get_by_ean(ean), work)

    @staticmethod
    def _view(product: Product | None, work: UnitOfWork) -> ProductView | None:
        if product is None:
            return None
        observed = []
        for listing in product.listings:
            store = work.stores.get(listing.store_slug)
            if store is None:  # pragma: no cover - a chave estrangeira não deixa acontecer
                continue
            observed.append(
                ObservedListing(
                    listing=listing,
                    store=store,
                    latest=work.observations.latest_for_listing(listing.listing_id),
                )
            )
        return ProductView(product=product, listings=observed)
