"""A passagem diária de recolha a uma loja.

É este o caso de uso que faz o sistema valer alguma coisa: cada dia que corre é um dia
de histórico que passa a existir, e cada dia que não corre é um dia perdido para sempre.

Três propriedades moldam o desenho:

**Idempotência.** Correr duas vezes no mesmo dia não duplica nem corrompe. A garantia
vem da chave natural do facto diário na base de dados, e não de o programa se lembrar de
que já correu.

**Gravação em lotes.** Uma passagem a milhares de páginas demora horas. Mantê-la toda
numa transação seguraria locks durante esse tempo e adiaria o histórico até ao fim. Como
cada observação é um facto independente e a escrita é idempotente, gravar em lotes é
seguro: uma passagem interrompida a meio deixa gravado o que já observou, que é
exatamente o que se quer.

**Parar quando a loja diz que não.** Um bloqueio não é uma falha de uma página: é a loja
a travar quem está a pedir. Continuar a percorrer o catálogo depois de um 429 transforma
um aviso num problema.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import structlog

from braunprices.domain.model.collection_run import CollectionReport, ObservedFailure
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import StoreListing
from braunprices.domain.model.scrape_outcome import ScrapeFailure
from braunprices.domain.ports.collection_reports import CollectionReportRepository
from braunprices.domain.ports.scraper import StoreScraper
from braunprices.domain.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug

logger = structlog.get_logger(__name__)

DEFAULT_BATCH_SIZE = 50


class StoreNotConfiguredError(Exception):
    """Pediu-se uma recolha a uma loja que não está registada."""


class Clock(Protocol):
    """Fonte do instante atual, injetável para que os testes o possam fixar."""

    def now(self) -> ObservedAt:
        """Instante atual, com fuso."""
        ...


class SystemClock:
    """O relógio do processo."""

    def now(self) -> ObservedAt:
        """Instante atual, em UTC."""
        return ObservedAt(datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Relógio parado, para testes que precisam de um instante conhecido."""

    instant: ObservedAt

    def now(self) -> ObservedAt:
        """Devolve sempre o mesmo instante."""
        return self.instant


@dataclass(frozen=True, slots=True)
class CollectStorePrices:
    """Percorre as referências ativas de uma loja e regista o que observar."""

    unit_of_work: UnitOfWorkFactory
    scraper: StoreScraper
    reports: CollectionReportRepository
    clock: Clock
    batch_size: int = DEFAULT_BATCH_SIZE

    def __call__(self, slug: StoreSlug, limit: int | None = None) -> CollectionReport:
        """Corre uma passagem a esta loja e devolve o relato do que aconteceu."""
        report = CollectionReport(
            run_id=uuid4(),
            store_slug=slug,
            started_at=self.clock.now(),
        )

        listings = self._plan(slug, report)
        logger.info(
            "recolha.iniciada",
            run_id=str(report.run_id),
            loja=slug.value,
            referencias=report.listings_planned,
        )

        pending: list[PriceObservation] = []
        for listing in listings[:limit] if limit is not None else listings:
            outcome = self.scraper.fetch(listing)

            if isinstance(outcome, ScrapeFailure):
                self._record_failure(report, listing, outcome)
                if outcome.should_stop_collecting_from_this_store:
                    report.stopped_early_because = outcome.detail
                    break
                continue

            pending.append(outcome.observation)
            report.pages_fetched += 1
            report.extraction_sources[outcome.source] += 1

            if len(pending) >= self.batch_size:
                self._persist(pending, report)
                pending = []

        if pending:
            self._persist(pending, report)

        report.finished_at = self.clock.now()
        self.reports.save(report)
        self._log_outcome(report)
        return report

    def _plan(self, slug: StoreSlug, report: CollectionReport) -> Sequence[StoreListing]:
        with self.unit_of_work() as work:
            if work.stores.get(slug) is None:
                message = (
                    f"A loja {slug} não está registada. Regista-a antes de pedir uma "
                    f"recolha, para que a política de ritmo dela exista."
                )
                raise StoreNotConfiguredError(message)
            listings = list(work.products.active_listings_for_store(slug))
        report.listings_planned = len(listings)
        return listings

    def _persist(self, observations: list[PriceObservation], report: CollectionReport) -> None:
        """Grava um lote e conta quantos preços mudaram de facto.

        A contagem é feita **antes** da escrita, comparando com a última observação
        conhecida de cada referência. Depois de gravar, a última passaria a ser a que
        se acabou de escrever, e nenhuma mudança seria detetada.
        """
        with self.unit_of_work() as work:
            report.prices_changed += self._count_changes(work, observations)
            report.observations_recorded += work.observations.add_all(observations)
            work.commit()

    @staticmethod
    def _count_changes(work: UnitOfWork, observations: list[PriceObservation]) -> int:
        changed = 0
        for observation in observations:
            previous = work.observations.latest_for_listing(observation.listing_id)
            if previous is not None and previous.price != observation.price:
                changed += 1
        return changed

    @staticmethod
    def _record_failure(
        report: CollectionReport, listing: StoreListing, failure: ScrapeFailure
    ) -> None:
        report.failures.append(
            ObservedFailure(
                listing_id=listing.listing_id,
                url=listing.url,
                reason=failure.reason,
                detail=failure.detail,
                http_status=failure.http_status,
            )
        )
        logger.warning(
            "recolha.falha",
            run_id=str(report.run_id),
            listing_id=str(listing.listing_id),
            url=listing.url,
            motivo=failure.reason.value,
            detalhe=failure.detail,
            status=failure.http_status,
        )

    @staticmethod
    def _log_outcome(report: CollectionReport) -> None:
        logger.info(
            "recolha.terminada",
            run_id=str(report.run_id),
            loja=report.store_slug.value,
            planeadas=report.listings_planned,
            tentadas=report.listings_attempted,
            paginas=report.pages_fetched,
            observacoes_novas=report.observations_recorded,
            precos_alterados=report.prices_changed,
            falhas=len(report.failures),
            falhas_por_motivo={
                reason.value: count for reason, count in report.failures_by_reason.items()
            },
            taxa_sucesso=round(report.success_rate, 4),
            taxa_recurso_html=round(report.fallback_rate, 4),
            parou_cedo=report.stopped_early_because,
            merece_investigacao=report.is_worth_investigating,
        )


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "Clock",
    "CollectStorePrices",
    "FixedClock",
    "StoreNotConfiguredError",
    "SystemClock",
]
