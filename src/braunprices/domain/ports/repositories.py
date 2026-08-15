"""Portos de persistência, definidos pelo domínio e implementados pela infraestrutura.

São ``Protocol`` estruturais: o domínio não conhece nenhuma implementação, e a
infraestrutura não precisa de herdar nada para satisfazer o contrato.

Repara no que **não** existe aqui: não há ``update`` nem ``delete`` para observações
de preço. A ausência é a interface. Um histórico append-only que dependesse de ninguém
chamar o método errado não seria append-only — seria uma convenção.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Protocol
from uuid import UUID

from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import Store
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.observation_cursor import ObservationCursor
from braunprices.domain.value_objects.store_slug import StoreSlug


class StoreRepository(Protocol):
    """Acesso às lojas configuradas."""

    def add(self, store: Store) -> None:
        """Regista uma loja nova."""
        ...

    def get(self, slug: StoreSlug) -> Store | None:
        """Devolve a loja com este slug, ou ``None`` se não existir."""
        ...

    def list_all(self) -> Sequence[Store]:
        """Devolve todas as lojas configuradas."""
        ...


class ProductRepository(Protocol):
    """Acesso aos produtos e às suas referências em lojas."""

    def add(self, product: Product) -> None:
        """Regista um produto novo com as referências que já tenha."""
        ...

    def save(self, product: Product) -> None:
        """Guarda alterações ao agregado: referências novas ou desativadas.

        Nunca toca em observações de preço. Um produto muda; o que se observou dele
        não muda.
        """
        ...

    def get(self, product_id: UUID) -> Product | None:
        """Devolve o produto com este identificador."""
        ...

    def get_by_ean(self, ean: EAN) -> Product | None:
        """Devolve o produto com este EAN, a chave de casamento entre lojas."""
        ...

    def get_by_listing(self, listing_id: UUID) -> Product | None:
        """Devolve o produto a que esta referência de loja pertence."""
        ...

    def active_listings_for_store(self, slug: StoreSlug) -> Sequence[StoreListing]:
        """Referências a visitar na próxima passagem de recolha desta loja."""
        ...


class PriceObservationRepository(Protocol):
    """Acesso ao histórico de observações — **append-only por contrato**."""

    def add_all(self, observations: Iterable[PriceObservation]) -> int:
        """Acrescenta observações ao histórico e devolve quantas ficaram gravadas.

        É idempotente por observação: correr a recolha duas vezes no mesmo dia não
        duplica nem corrompe. Uma observação já existente é ignorada em silêncio, e o
        número devolvido conta apenas as que entraram de facto.
        """
        ...

    def history_for_listing(
        self,
        listing_id: UUID,
        since: date | None = None,
        until: date | None = None,
    ) -> Sequence[PriceObservation]:
        """Observações desta referência, por instante crescente.

        ``since`` e ``until`` são dias de Lisboa, ambos inclusivos.
        """
        ...

    def page_for_listing(
        self,
        listing_id: UUID,
        *,
        since: date | None = None,
        until: date | None = None,
        after: ObservationCursor | None = None,
        limit: int = 100,
    ) -> Sequence[PriceObservation]:
        """Um troço do histórico desta referência, por instante crescente.

        A posição é o último facto lido (``after``) e não um deslocamento: num
        histórico a que se acrescentam factos, paginar por ``OFFSET`` devolveria
        repetições ou saltos sem nada o assinalar.
        """
        ...

    def latest_for_listing(self, listing_id: UUID) -> PriceObservation | None:
        """Última observação registada desta referência."""
        ...

    def observed_on(self, listing_id: UUID, day: date) -> Sequence[PriceObservation]:
        """Observações desta referência num dia de Lisboa."""
        ...
