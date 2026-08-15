"""Porto de persistência dos relatos de recolha."""

from collections.abc import Sequence
from typing import Protocol

from braunprices.domain.model.collection_run import CollectionReport
from braunprices.domain.value_objects.store_slug import StoreSlug


class CollectionReportRepository(Protocol):
    """Guarda e devolve o que aconteceu em cada passagem.

    Os relatos são guardados, e não apenas registados num log: uma degradação
    silenciosa reconhece-se ao comparar hoje com a semana passada, e isso exige que a
    semana passada ainda exista em algum lado consultável.
    """

    def save(self, report: CollectionReport) -> None:
        """Guarda ou atualiza o relato desta passagem."""
        ...

    def recent_for_store(self, slug: StoreSlug, limit: int = 30) -> Sequence[CollectionReport]:
        """Últimas passagens a esta loja, da mais recente para trás."""
        ...
