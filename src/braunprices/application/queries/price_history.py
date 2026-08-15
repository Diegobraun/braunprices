"""O histórico observado de uma referência de loja.

É a consulta que dá corpo à afirmação pública do sistema: este preço, neste dia, nesta
página. Devolve factos com proveniência, e nunca uma média, uma estimativa ou um dia
interpolado — o histórico é discreto e afirma apenas o que foi visto.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import Store
from braunprices.domain.ports.unit_of_work import UnitOfWorkFactory
from braunprices.domain.value_objects.observation_cursor import ObservationCursor

# Quantos factos por página, e o teto acima do qual o pedido é recusado. O teto existe
# para que uma página não se transforme num despejo da base de dados por engano.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


class PageSizeOutOfRangeError(Exception):
    """Pediu-se uma página maior do que o teto, ou de tamanho não positivo."""


@dataclass(frozen=True, slots=True)
class HistoryPage:
    """Um troço do histórico, com o que é preciso para pedir o troço seguinte."""

    listing: StoreListing
    store: Store
    product: Product
    observations: Sequence[PriceObservation]
    next_cursor: ObservationCursor | None

    @property
    def has_more(self) -> bool:
        """Indica se ficou histórico por ler a seguir a esta página."""
        return self.next_cursor is not None


@dataclass(frozen=True, slots=True)
class GetPriceHistory:
    """Devolve o histórico observado de uma referência, página a página."""

    unit_of_work: UnitOfWorkFactory

    def __call__(
        self,
        listing_id: UUID,
        *,
        since: date | None = None,
        until: date | None = None,
        after: ObservationCursor | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> HistoryPage | None:
        """Devolve a página pedida, ou ``None`` se a referência não existir."""
        if not 0 < limit <= MAX_PAGE_SIZE:
            message = (
                f"limit={limit} fora do intervalo aceite (0, {MAX_PAGE_SIZE}]. "
                f"Uma página maior do que isto é um despejo, não uma página."
            )
            raise PageSizeOutOfRangeError(message)

        with self.unit_of_work() as work:
            product = work.products.get_by_listing(listing_id)
            if product is None:
                return None
            listing = product.listing(listing_id)
            store = work.stores.get(listing.store_slug)
            if store is None:  # pragma: no cover - a chave estrangeira não deixa acontecer
                return None

            # Pede-se um facto a mais do que o pedido para saber se há página seguinte
            # sem ter de contar o histórico todo — uma contagem que cresce todos os dias.
            found = work.observations.page_for_listing(
                listing_id, since=since, until=until, after=after, limit=limit + 1
            )

        observations = list(found[:limit])
        next_cursor = (
            ObservationCursor.after(observations[-1])
            if len(found) > limit and observations
            else None
        )
        return HistoryPage(
            listing=listing,
            store=store,
            product=product,
            observations=observations,
            next_cursor=next_cursor,
        )
