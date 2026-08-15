"""Montagem das peças concretas — o *composition root*.

É o único sítio onde tudo se conhece: engine, cliente HTTP, adaptadores de loja e casos
de uso. Isolá-lo aqui é o que mantém o resto do código a depender de portos e não de
implementações.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx

from braunprices.application.use_cases.collect_store_prices import (
    CollectStorePrices,
    SystemClock,
)
from braunprices.domain.model.collection_run import CollectionReport
from braunprices.domain.model.store import Store
from braunprices.domain.ports.scraper import StoreScraper
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.config import Settings
from braunprices.infrastructure.persistence.engine import build_engine
from braunprices.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from braunprices.infrastructure.scraping.http_client import CollectionHttpClient
from braunprices.infrastructure.scraping.rate_limiter import DomainRateLimiter
from braunprices.infrastructure.scraping.robots import RobotsPolicy
from braunprices.infrastructure.scraping.worten import WORTEN_SLUG, WortenScraper

# Adaptadores conhecidos, por loja. Uma loja registada na base de dados sem adaptador
# aqui é um erro de configuração e não uma recolha vazia — daí falhar explicitamente.
SCRAPERS: dict[StoreSlug, Callable[[Store, CollectionHttpClient], StoreScraper]] = {
    WORTEN_SLUG: WortenScraper,
}


class NoScraperForStoreError(Exception):
    """Pediu-se uma recolha a uma loja para a qual não existe adaptador."""


@dataclass(frozen=True, slots=True)
class Container:
    """As peças montadas, prontas a usar."""

    settings: Settings
    unit_of_work: Callable[[], SqlUnitOfWork]
    http_client: CollectionHttpClient

    def scraper_for(self, store: Store) -> StoreScraper:
        """Devolve o adaptador desta loja."""
        build = SCRAPERS.get(store.slug)
        if build is None:
            message = (
                f"Não há adaptador para {store.slug}. As lojas com adaptador são: "
                f"{sorted(slug.value for slug in SCRAPERS)}."
            )
            raise NoScraperForStoreError(message)
        return build(store, self.http_client)

    def collect_prices_for(self, store: Store) -> CollectStorePrices:
        """Monta o caso de uso da passagem diária para esta loja."""
        return CollectStorePrices(
            unit_of_work=self.unit_of_work,
            scraper=self.scraper_for(store),
            reports=_ReportsThroughUnitOfWork(self.unit_of_work),
            clock=SystemClock(),
        )


@dataclass(frozen=True, slots=True)
class _ReportsThroughUnitOfWork:
    """Guarda relatos numa transação própria.

    O relato tem de ser gravado mesmo quando a passagem correu mal — sobretudo quando
    correu mal. Partilhar a transação dos lotes de observações faria com que uma falha
    a gravar observações levasse consigo o registo de que essa falha aconteceu.
    """

    unit_of_work: Callable[[], SqlUnitOfWork]

    def save(self, report: CollectionReport) -> None:
        """Grava o relato e confirma de imediato."""
        with self.unit_of_work() as work:
            work.reports.save(report)
            work.commit()

    def recent_for_store(self, slug: StoreSlug, limit: int = 30) -> Sequence[CollectionReport]:
        """Últimas passagens a esta loja."""
        with self.unit_of_work() as work:
            return work.reports.recent_for_store(slug, limit)


def build_container(settings: Settings) -> Container:
    """Monta tudo a partir das definições."""
    engine = build_engine(settings.database_url)
    http = httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
    )
    return Container(
        settings=settings,
        unit_of_work=lambda: SqlUnitOfWork(engine),
        http_client=CollectionHttpClient(
            user_agent=settings.user_agent,
            robots=RobotsPolicy(user_agent=settings.user_agent, http_client=http),
            rate_limiter=DomainRateLimiter(),
            http_client=http,
        ),
    )
