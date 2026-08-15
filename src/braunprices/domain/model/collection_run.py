"""O relato de uma passagem de recolha.

Existe para responder a uma pergunta que o sistema não consegue responder sozinho:
**onde é que a recolha está a falhar em silêncio?**

Um scraper que rebenta grita e alguém repara. Um scraper que passa a devolver o preço
errado, ou que deixa de encontrar metade do catálogo porque a loja mudou a marcação,
continua verde e envenena o histórico durante semanas. Como o valor do produto é o
histórico acumulado, e como esse histórico não se recupera depois, detetar isto tarde é
a falha mais cara que este sistema pode ter.

Por isso a passagem conta tudo — páginas, falhas por motivo, preços que mudaram, quantas
observações vieram do recurso ao HTML — e o relato é guardado, não apenas registado num
log que ninguém relê.
"""

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from braunprices.domain.model.scrape_outcome import ExtractionSource, FailureReason
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug


@dataclass(frozen=True, slots=True)
class ObservedFailure:
    """Uma falha concreta, com o suficiente para a investigar depois."""

    listing_id: UUID
    url: str
    reason: FailureReason
    detail: str
    http_status: int | None = None


@dataclass
class CollectionReport:
    """O que aconteceu numa passagem a uma loja."""

    run_id: UUID
    store_slug: StoreSlug
    started_at: ObservedAt
    finished_at: ObservedAt | None = None
    listings_planned: int = 0
    pages_fetched: int = 0
    observations_recorded: int = 0
    prices_changed: int = 0
    failures: list[ObservedFailure] = field(default_factory=list)
    extraction_sources: Counter[ExtractionSource] = field(default_factory=Counter)
    stopped_early_because: str | None = None

    @property
    def listings_attempted(self) -> int:
        """Quantas referências chegaram a ser tentadas."""
        return self.pages_fetched + len(self.failures)

    @property
    def failures_by_reason(self) -> dict[FailureReason, int]:
        """Contagem de falhas por motivo, que é como se lê uma degradação."""
        return dict(Counter(failure.reason for failure in self.failures))

    @property
    def success_rate(self) -> float:
        """Fração das tentativas que produziu uma observação, entre 0 e 1.

        Devolve 1.0 quando não houve tentativas: uma passagem sem trabalho não falhou.
        """
        attempted = self.listings_attempted
        return 1.0 if attempted == 0 else self.pages_fetched / attempted

    @property
    def fallback_rate(self) -> float:
        """Fração das observações que veio do recurso ao HTML, entre 0 e 1.

        É o número que denuncia uma loja a mudar de marcação: continua a devolver
        preços, e sem isto ninguém daria por isso.
        """
        total = sum(self.extraction_sources.values())
        if total == 0:
            return 0.0
        return self.extraction_sources[ExtractionSource.HTML_FALLBACK] / total

    @property
    def was_blocked(self) -> bool:
        """Indica se a loja recusou o acesso durante esta passagem."""
        return any(failure.reason.is_the_store_saying_no for failure in self.failures)

    @property
    def is_worth_investigating(self) -> bool:
        """Indica se esta passagem merece que um humano lhe pegue.

        Os limiares são deliberadamente sensíveis: o custo de investigar uma passagem
        que afinal estava bem é meia hora; o custo de não investigar uma que estava mal
        são semanas de histórico envenenado.
        """
        return (
            self.was_blocked
            or self.success_rate < SUSPICIOUS_SUCCESS_RATE
            or self.fallback_rate > SUSPICIOUS_FALLBACK_RATE
        )


# Abaixo desta taxa de sucesso, alguma coisa mudou do outro lado.
SUSPICIOUS_SUCCESS_RATE = 0.95

# Acima desta fração de recurso ao HTML, o JSON-LD deixou de ser a fonte fiável que se
# assumiu — e é melhor saber isso antes de a marcação desaparecer de vez.
SUSPICIOUS_FALLBACK_RATE = 0.10
