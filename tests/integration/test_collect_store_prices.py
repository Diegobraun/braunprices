"""A passagem diária, ponta a ponta contra Postgres real.

O único duplo aqui é o scraper, e é deliberado: o que está sob teste é a orquestração,
não a extração — essa tem os seus testes contra HTML real capturado. Tudo o resto é
verdadeiro, incluindo a base de dados e as migrações.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text

from braunprices.application.use_cases.collect_store_prices import (
    CollectStorePrices,
    FixedClock,
    StoreNotConfiguredError,
)
from braunprices.domain.model.availability import Availability
from braunprices.domain.model.collection_run import CollectionReport
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import StoreListing
from braunprices.domain.model.scrape_outcome import (
    ExtractionSource,
    FailureReason,
    ScrapedListing,
    ScrapeFailure,
    ScrapeOutcome,
)
from braunprices.domain.rules.price_reference import lowest_price_in_window
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure import composition
from braunprices.infrastructure.composition import build_container
from braunprices.infrastructure.config import Settings
from braunprices.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from tests.integration.factories import a_listing, a_product, a_store

STORE = StoreSlug("loja-exemplo")
NOW = ObservedAt(datetime(2026, 8, 15, 9, 0, tzinfo=UTC))


def scraped(
    listing: StoreListing,
    price: str,
    *,
    availability: Availability = Availability.IN_STOCK,
    source: ExtractionSource = ExtractionSource.JSON_LD,
    observed_at: ObservedAt = NOW,
) -> ScrapedListing:
    """Desfecho bem-sucedido para esta referência, como o adaptador o devolveria."""
    return ScrapedListing(
        observation=PriceObservation(
            listing_id=listing.listing_id,
            store_slug=STORE,
            observed_at=observed_at,
            price=Money.of(Decimal(price)),
            availability=availability,
            source_url=listing.url,
            raw_hash=f"sha256:{listing.external_id}-{price}",
        ),
        product_name=f"Produto {listing.external_id}",
        ean=None,
        source=source,
    )


@dataclass
class ScriptedScraper:
    """Devolve desfechos combinados por referência, e regista o que foi visitado."""

    outcomes: dict[str, ScrapeOutcome] = field(default_factory=dict)
    default_price: str = "59.99"
    observed_at: ObservedAt = NOW
    visited: list[str] = field(default_factory=list)

    @property
    def store_slug(self) -> StoreSlug:
        """A loja que este duplo sabe ler."""
        return STORE

    def fetch(self, listing: StoreListing) -> ScrapeOutcome:
        """Devolve o desfecho combinado para esta referência, ou um preço normal."""
        self.visited.append(listing.external_id)
        combined = self.outcomes.get(listing.external_id)
        if combined is not None:
            return combined
        return scraped(listing, self.default_price, observed_at=self.observed_at)


def _look_at_nothing() -> None:
    """Espreitadela por omissão, que não faz nada."""


@dataclass
class WatchingScraper(ScriptedScraper):
    """Como o anterior, mas deixa alguém espreitar a base a cada página pedida."""

    watcher: Callable[[], None] = _look_at_nothing

    def fetch(self, listing: StoreListing) -> ScrapeOutcome:
        """Espreita antes de devolver o desfecho desta referência."""
        self.watcher()
        return super().fetch(listing)


@dataclass
class InMemoryReports:
    """Guarda relatos em memória, para os testes que não estão a testar a persistência."""

    saved: list[CollectionReport] = field(default_factory=list)

    def save(self, report: CollectionReport) -> None:
        """Acrescenta o relato à lista."""
        self.saved.append(report)

    def recent_for_store(self, slug: StoreSlug, limit: int = 30) -> Sequence[CollectionReport]:
        """Últimos relatos guardados desta loja."""
        return [report for report in self.saved if report.store_slug == slug][-limit:]


@dataclass(frozen=True)
class PersistedReports:
    """Grava relatos em transação própria, como o composition root faz em produção."""

    engine: Engine

    def save(self, report: CollectionReport) -> None:
        """Grava o relato e confirma de imediato."""
        with SqlUnitOfWork(self.engine) as work:
            work.reports.save(report)
            work.commit()

    def recent_for_store(self, slug: StoreSlug, limit: int = 30) -> Sequence[CollectionReport]:
        """Últimas passagens gravadas desta loja."""
        with SqlUnitOfWork(self.engine) as work:
            return work.reports.recent_for_store(slug, limit)


@pytest.fixture
def clean_database(migrated_engine: Engine) -> Iterator[None]:
    """Deixa a base vazia no fim.

    Estes testes precisam de commits verdadeiros — a idempotência é uma propriedade da
    base de dados e não do processo — e por isso não há transação envolvente a apanhar
    a limpeza.
    """
    yield
    with migrated_engine.begin() as cleanup:
        cleanup.execute(
            text(
                "TRUNCATE collection_failures, collection_runs, price_observations, "
                "store_listings, products, stores RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def listings(migrated_engine: Engine, clean_database: None) -> list[StoreListing]:
    """Uma loja registada com três referências ativas."""
    prepared = [a_listing("loja-exemplo", str(number)) for number in (1, 2, 3)]
    with SqlUnitOfWork(migrated_engine) as work:
        work.stores.add(a_store())
        work.products.add(a_product(listings=prepared))
        work.commit()
    return prepared


def collector(
    engine: Engine,
    scraper: ScriptedScraper | None = None,
    reports: InMemoryReports | PersistedReports | None = None,
    batch_size: int = 50,
) -> CollectStorePrices:
    """Monta o caso de uso com relógio parado."""
    return CollectStorePrices(
        unit_of_work=lambda: SqlUnitOfWork(engine),
        scraper=scraper if scraper is not None else ScriptedScraper(),
        reports=reports if reports is not None else InMemoryReports(),
        clock=FixedClock(NOW),
        batch_size=batch_size,
    )


# -- a passagem que corre bem ---------------------------------------------


def test_a_pass_records_one_observation_per_listing(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    report = collector(migrated_engine)(STORE)

    assert report.listings_planned == 3
    assert report.pages_fetched == 3
    assert report.observations_recorded == 3
    assert report.failures == []
    assert report.success_rate == 1.0
    assert report.finished_at is not None

    with SqlUnitOfWork(migrated_engine) as work:
        for listing in listings:
            history = work.observations.history_for_listing(listing.listing_id)
            assert len(history) == 1
            assert history[0].listing_id == listing.listing_id
            assert history[0].source_url == listing.url


def test_running_twice_on_the_same_day_does_not_duplicate(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # É esta propriedade que permite repetir sem medo uma passagem interrompida a meio.
    collect = collector(migrated_engine)

    first = collect(STORE)
    second = collect(STORE)

    assert first.observations_recorded == 3
    assert second.observations_recorded == 0
    assert second.pages_fetched == 3  # visitou na mesma; só não teve nada de novo a gravar

    with SqlUnitOfWork(migrated_engine) as work:
        for listing in listings:
            assert len(work.observations.history_for_listing(listing.listing_id)) == 1


def test_a_price_change_between_passes_is_recorded_and_counted(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Passagens em dias diferentes, como em produção: a de ontem a 59,99 €, a de hoje
    # a 49,99 €.
    yesterday = ObservedAt(datetime(2026, 8, 14, 9, 0, tzinfo=UTC))
    collector(migrated_engine, ScriptedScraper(default_price="59.99", observed_at=yesterday))(STORE)
    second = collector(migrated_engine, ScriptedScraper(default_price="49.99"))(STORE)

    assert second.observations_recorded == 3
    assert second.prices_changed == 3

    with SqlUnitOfWork(migrated_engine) as work:
        history = work.observations.history_for_listing(listings[0].listing_id)
    assert [item.price.amount for item in history] == [Decimal("59.99"), Decimal("49.99")]


def test_two_prices_no_mesmo_dia_sao_dois_factos(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Idempotência não é "uma observação por dia": é "o mesmo facto não entra duas
    # vezes". Uma loja que baixa o preço à tarde praticou os dois preços nesse dia, e
    # apagar o primeiro seria apagar precisamente o que a lei manda saber.
    morning = ObservedAt(datetime(2026, 8, 15, 7, 0, tzinfo=UTC))
    afternoon = ObservedAt(datetime(2026, 8, 15, 15, 0, tzinfo=UTC))
    collector(migrated_engine, ScriptedScraper(default_price="59.99", observed_at=morning))(STORE)
    collector(migrated_engine, ScriptedScraper(default_price="49.99", observed_at=afternoon))(STORE)

    with SqlUnitOfWork(migrated_engine) as work:
        same_day = work.observations.observed_on(listings[0].listing_id, date(2026, 8, 15))
    assert [item.price.amount for item in same_day] == [Decimal("59.99"), Decimal("49.99")]


def test_an_unchanged_price_counts_as_no_change(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    collect = collector(migrated_engine)
    collect(STORE)
    assert collect(STORE).prices_changed == 0


def test_the_first_observation_of_a_listing_is_not_a_price_change(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Não havia preço anterior. Contá-lo como alteração faria a primeira passagem de
    # cada loja parecer um dia de promoções em massa.
    assert collector(migrated_engine)(STORE).prices_changed == 0


def test_batches_are_written_as_the_pass_goes_and_not_only_at_the_end(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Uma passagem de horas que só gravasse no fim perderia tudo ao ser interrompida —
    # e o histórico de um dia não se recupera. Contar as observações já visíveis a
    # meio da passagem, de fora da transação dela, é o que distingue as duas coisas.
    observed_along_the_way: list[int] = []

    def count_committed_observations() -> int:
        with migrated_engine.connect() as separate:
            return int(
                separate.execute(text("SELECT count(*) FROM price_observations")).scalar_one()
            )

    scraper = WatchingScraper(
        watcher=lambda: observed_along_the_way.append(count_committed_observations())
    )
    report = collector(migrated_engine, scraper, batch_size=1)(STORE)

    assert report.observations_recorded == 3
    # Antes da 1.ª, da 2.ª e da 3.ª página: nada, uma, duas — já gravadas e confirmadas.
    assert observed_along_the_way == [0, 1, 2]


def test_the_limit_option_visits_only_that_many_listings(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    scraper = ScriptedScraper()
    report = collector(migrated_engine, scraper)(STORE, limit=2)
    assert len(scraper.visited) == 2
    assert report.pages_fetched == 2


def test_only_active_listings_are_visited(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    with SqlUnitOfWork(migrated_engine) as work:
        product = work.products.get_by_listing(listings[0].listing_id)
        assert product is not None
        product.deactivate_listing(listings[0].listing_id)
        work.products.save(product)
        work.commit()

    scraper = ScriptedScraper()
    report = collector(migrated_engine, scraper)(STORE)

    assert report.listings_planned == 2
    assert listings[0].external_id not in scraper.visited


def test_a_pass_over_a_store_without_listings_is_not_a_failure(
    migrated_engine: Engine, clean_database: None
) -> None:
    with SqlUnitOfWork(migrated_engine) as work:
        work.stores.add(a_store("loja-vazia"))
        work.commit()

    report = collector(migrated_engine)(StoreSlug("loja-vazia"))

    assert report.listings_planned == 0
    assert report.success_rate == 1.0
    assert report.is_worth_investigating is False


def test_each_pass_gets_its_own_identifier(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    collect = collector(migrated_engine)
    assert collect(STORE).run_id != collect(STORE).run_id


# -- quando corre mal ------------------------------------------------------


def test_a_failure_on_one_listing_does_not_stop_the_others(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    scraper = ScriptedScraper(
        outcomes={
            "2": ScrapeFailure(
                reason=FailureReason.MARKUP_MISSING, detail="A página mudou de marcação."
            )
        }
    )
    report = collector(migrated_engine, scraper)(STORE)

    assert len(scraper.visited) == 3
    assert report.pages_fetched == 2
    assert report.failures_by_reason == {FailureReason.MARKUP_MISSING: 1}
    assert report.success_rate == pytest.approx(2 / 3)


def test_a_block_stops_the_whole_pass_right_there(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Um bloqueio não é uma falha de uma página: é a loja a travar quem está a pedir.
    # Continuar a percorrer o catálogo depois de um 429 transforma um aviso num problema.
    scraper = ScriptedScraper(
        outcomes={
            "1": ScrapeFailure(
                reason=FailureReason.BLOCKED,
                detail="A loja respondeu 429.",
                http_status=429,
            )
        }
    )
    report = collector(migrated_engine, scraper)(STORE)

    assert scraper.visited == ["1"]
    assert report.stopped_early_because is not None
    assert "429" in report.stopped_early_because
    assert report.was_blocked is True
    assert report.is_worth_investigating is True


def test_a_robots_refusal_also_stops_the_pass(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    scraper = ScriptedScraper(
        outcomes={
            "1": ScrapeFailure(
                reason=FailureReason.DISALLOWED_BY_ROBOTS,
                detail="O robots.txt não permite este caminho.",
            )
        }
    )
    report = collector(migrated_engine, scraper)(STORE)

    assert scraper.visited == ["1"]
    assert report.was_blocked is True


def test_what_was_collected_before_a_block_is_kept(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    scraper = ScriptedScraper(
        outcomes={"3": ScrapeFailure(reason=FailureReason.BLOCKED, detail="429", http_status=429)}
    )
    report = collector(migrated_engine, scraper, batch_size=1)(STORE)

    assert report.observations_recorded == 2
    with SqlUnitOfWork(migrated_engine) as work:
        assert len(work.observations.history_for_listing(listings[0].listing_id)) == 1


def test_collecting_from_a_store_that_is_not_registered_fails_explicitly(
    migrated_engine: Engine, clean_database: None
) -> None:
    with pytest.raises(StoreNotConfiguredError, match="não está registada"):
        collector(migrated_engine)(StoreSlug("nao-existe"))


# -- observabilidade -------------------------------------------------------


def test_the_pass_counts_where_each_observation_came_from(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # É este número que denuncia uma loja a mudar de marcação sem deixar de dar preços.
    scraper = ScriptedScraper(
        outcomes={"2": scraped(listings[1], "59.99", source=ExtractionSource.HTML_FALLBACK)}
    )
    report = collector(migrated_engine, scraper)(STORE)

    assert report.extraction_sources[ExtractionSource.JSON_LD] == 2
    assert report.extraction_sources[ExtractionSource.HTML_FALLBACK] == 1
    assert report.fallback_rate == pytest.approx(1 / 3)
    assert report.is_worth_investigating is True


def test_a_clean_pass_is_not_flagged_for_investigation(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    assert collector(migrated_engine)(STORE).is_worth_investigating is False


def test_the_report_is_persisted_with_its_failures(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Guardado, e não apenas registado num log: uma degradação reconhece-se ao comparar
    # hoje com a semana passada, e isso exige que a semana passada ainda exista.
    scraper = ScriptedScraper(
        outcomes={"2": ScrapeFailure(reason=FailureReason.TIMEOUT, detail="o pedido expirou")}
    )
    reports = PersistedReports(migrated_engine)
    written = collector(migrated_engine, scraper, reports)(STORE)

    stored = reports.recent_for_store(STORE)
    assert len(stored) == 1
    assert stored[0].run_id == written.run_id
    assert stored[0].pages_fetched == 2
    assert stored[0].failures_by_reason == {FailureReason.TIMEOUT: 1}
    assert stored[0].failures[0].url.endswith("/2")
    assert stored[0].failures[0].listing_id == listings[1].listing_id
    assert stored[0].finished_at is not None
    assert stored[0].extraction_sources[ExtractionSource.JSON_LD] == 2


def test_saving_the_same_report_twice_does_not_duplicate_its_failures(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    scraper = ScriptedScraper(
        outcomes={"2": ScrapeFailure(reason=FailureReason.TIMEOUT, detail="o pedido expirou")}
    )
    reports = PersistedReports(migrated_engine)
    report = collector(migrated_engine, scraper, reports)(STORE)
    reports.save(report)

    stored = reports.recent_for_store(STORE)
    assert len(stored) == 1
    assert len(stored[0].failures) == 1


def test_passes_come_back_from_the_most_recent_backwards(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    reports = PersistedReports(migrated_engine)
    older = CollectStorePrices(
        unit_of_work=lambda: SqlUnitOfWork(migrated_engine),
        scraper=ScriptedScraper(),
        reports=reports,
        clock=FixedClock(ObservedAt(datetime(2026, 8, 14, 9, 0, tzinfo=UTC))),
    )(STORE)
    newer = collector(migrated_engine, reports=reports)(STORE)

    assert [report.run_id for report in reports.recent_for_store(STORE)] == [
        newer.run_id,
        older.run_id,
    ]
    assert [report.run_id for report in reports.recent_for_store(STORE, limit=1)] == [newer.run_id]


def test_the_report_of_another_store_is_not_mixed_in(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    reports = PersistedReports(migrated_engine)
    collector(migrated_engine, reports=reports)(STORE)

    with SqlUnitOfWork(migrated_engine) as work:
        work.stores.add(a_store("outra-loja"))
        work.commit()
    assert reports.recent_for_store(StoreSlug("outra-loja")) == []


def test_the_report_is_committed_apart_from_the_batches(
    migrated_engine: Engine, listings: list[StoreListing], monkeypatch: pytest.MonkeyPatch
) -> None:
    # O relato tem de ficar gravado mesmo quando a passagem correu mal — sobretudo
    # quando correu mal. Partilhar a transação dos lotes faria com que uma falha a
    # gravar observações levasse consigo o registo de que essa falha aconteceu.
    monkeypatch.setattr(composition, "build_engine", lambda _url: migrated_engine)
    container = build_container(Settings())
    store = a_store()
    monkeypatch.setitem(composition.SCRAPERS, STORE, lambda _store, _client: ScriptedScraper())
    reports = container.collect_prices_for(store).reports

    report = CollectionReport(run_id=uuid4(), store_slug=STORE, started_at=NOW)
    reports.save(report)

    # Um lote que abre e não confirma, como aconteceria numa passagem interrompida.
    with SqlUnitOfWork(migrated_engine) as work:
        work.observations.add_all([scraped(listings[0], "59.99").observation])

    assert [saved.run_id for saved in reports.recent_for_store(STORE)] == [report.run_id]
    with SqlUnitOfWork(migrated_engine) as work:
        assert work.observations.history_for_listing(listings[0].listing_id) == []


# -- o que a passagem deixa para o resto do sistema ------------------------


def test_an_observation_that_does_not_count_as_practised_is_still_recorded(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # Uma observação sem disponibilidade legível continua a ser um facto observado. O
    # que ela não faz é entrar no cálculo da janela legal.
    scraper = ScriptedScraper(
        outcomes={"1": scraped(listings[0], "59.99", availability=Availability.UNKNOWN)}
    )
    report = collector(migrated_engine, scraper)(STORE)
    assert report.observations_recorded == 3

    with SqlUnitOfWork(migrated_engine) as work:
        history = work.observations.history_for_listing(listings[0].listing_id)
    assert history[0].availability is Availability.UNKNOWN
    assert history[0].counts_as_price_practised is False


def test_the_history_it_writes_feeds_the_thirty_day_rule(
    migrated_engine: Engine, listings: list[StoreListing]
) -> None:
    # O ponto de todo o resto: o que a recolha grava tem de servir, sem tradução, à
    # regra do Decreto-Lei 109-G/2021.
    collector(migrated_engine, ScriptedScraper(default_price="80.00"))(STORE)

    with SqlUnitOfWork(migrated_engine) as work:
        history = work.observations.history_for_listing(listings[0].listing_id)
    assert lowest_price_in_window(history, date(2026, 8, 16)) == Money.of("80.00")
