"""Observação de preço: o facto histórico que este sistema existe para acumular.

Uma observação é imutável. Nunca se corrige, nunca se apaga. Se o preço mudou,
escreve-se outra observação; se a extração estava errada, escreve-se outro facto e
regista-se a suspeita **ao lado**, sem tocar no valor original.

Esta imutabilidade não é preferência de estilo: é a única razão pela qual as
afirmações públicas do sistema valem alguma coisa. Um histórico que se pode editar
não prova nada sobre ninguém.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from braunprices.domain.errors import DomainError
from braunprices.domain.model.availability import Availability
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """Um preço lido numa página, num instante, com a proveniência registada.

    ``raw_hash`` é a impressão digital do conteúdo de onde o preço foi extraído.
    Serve dois fins: detetar que a página não mudou entre passagens, e permitir
    verificar mais tarde de que exato conteúdo saiu este número.
    """

    listing_id: UUID
    store_slug: StoreSlug
    observed_at: ObservedAt
    price: Money
    availability: Availability
    source_url: str
    raw_hash: str

    def __post_init__(self) -> None:
        if not self.source_url.startswith(("http://", "https://")):
            raise DomainError(f"source_url={self.source_url!r} não é um URL absoluto.")
        if not self.raw_hash.strip():
            raise DomainError(
                "Uma observação sem raw_hash não tem proveniência verificável e não é aceite."
            )
        object.__setattr__(self, "raw_hash", self.raw_hash.strip())

    @property
    def counts_as_price_practised(self) -> bool:
        """Indica se esta observação entra no cálculo da janela legal."""
        return self.availability.counts_as_price_practised

    @property
    def local_date(self) -> date:
        """Dia de Lisboa a que a observação pertence."""
        return self.observed_at.local_date
