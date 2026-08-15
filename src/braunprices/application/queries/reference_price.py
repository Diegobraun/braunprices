"""O preço de referência de uma referência de loja, numa data.

É a pergunta que dá razão de ser ao projeto: se esta loja anunciasse hoje uma redução
nesta página, que preço teria de indicar como anterior?

A resposta vem sempre acompanhada da regra que a produziu, da janela considerada e de
quantas observações entraram na conta. Um número sem isso não é verificável por quem o
lê — e este sistema publica afirmações sobre empresas identificadas.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.price_window import DEFAULT_WINDOW_DAYS, PriceWindow
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.ports.unit_of_work import UnitOfWorkFactory
from braunprices.domain.rules.price_reference import (
    ReferencePrice,
    lowest_price_in_window,
    reference_price_for_announcement,
)
from braunprices.domain.value_objects.money import Money

_ONE_DAY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class ReferencePriceAnswer:
    """O que se sabe sobre a janela legal desta referência, nesta data."""

    listing: StoreListing
    product: Product
    window: PriceWindow
    lowest_in_window: Money | None
    reference: ReferencePrice | None
    latest: PriceObservation | None
    observations_considered: int

    @property
    def has_enough_history(self) -> bool:
        """Indica se houve alguma observação elegível na janela.

        Sem observações não se responde zero nem se estima: responde-se que não se
        sabe. Um produto sobre o qual não há dados não esteve a custar nada.
        """
        return self.reference is not None


@dataclass(frozen=True, slots=True)
class GetReferencePrice:
    """Aplica a regra dos 30 dias ao histórico observado de uma referência."""

    unit_of_work: UnitOfWorkFactory

    def __call__(
        self,
        listing_id: UUID,
        reference_date: date,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> ReferencePriceAnswer | None:
        """Devolve a resposta, ou ``None`` se a referência não existir."""
        window = PriceWindow(reference_date=reference_date, window_days=window_days)

        with self.unit_of_work() as work:
            product = work.products.get_by_listing(listing_id)
            if product is None:
                return None
            listing = product.listing(listing_id)
            # A janela é fechada à esquerda e aberta à direita; `until` do repositório é
            # inclusivo, daí o dia anterior ao da aplicação do desconto.
            observations = work.observations.history_for_listing(
                listing_id, since=window.start, until=_last_day_inside(window)
            )
            latest = work.observations.latest_for_listing(listing_id)

        return ReferencePriceAnswer(
            listing=listing,
            product=product,
            window=window,
            lowest_in_window=lowest_price_in_window(observations, reference_date, window_days),
            reference=reference_price_for_announcement(observations, reference_date, window_days),
            latest=latest,
            observations_considered=_eligible_count(observations, window),
        )


def _last_day_inside(window: PriceWindow) -> date:
    """Último dia que ainda pertence à janela."""
    return window.end_exclusive - _ONE_DAY


def _eligible_count(observations: Sequence[PriceObservation], window: PriceWindow) -> int:
    """Quantas observações contam como preço praticado dentro da janela."""
    return sum(
        1
        for observation in observations
        if window.contains(observation.local_date) and observation.counts_as_price_practised
    )
