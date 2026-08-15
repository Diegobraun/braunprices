"""Persistência dos relatos de recolha."""

from collections import Counter
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import Connection, delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from braunprices.domain.model.collection_run import CollectionReport, ObservedFailure
from braunprices.domain.model.scrape_outcome import ExtractionSource, FailureReason
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.persistence import tables


class SqlCollectionReportRepository:
    """Guarda e devolve o que aconteceu em cada passagem, em PostgreSQL."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def save(self, report: CollectionReport) -> None:
        """Guarda ou atualiza o relato desta passagem.

        Ao contrário das observações de preço, um relato **pode** ser reescrito: é um
        resumo de uma execução em curso, não um facto histórico sobre uma loja. Uma
        passagem que ainda não terminou tem `finished_at` a nulo, e o mesmo relato é
        gravado outra vez quando terminar.
        """
        statement = postgres_insert(tables.collection_runs).values(
            run_id=report.run_id,
            store_slug=report.store_slug.value,
            started_at=report.started_at.instant,
            finished_at=report.finished_at.instant if report.finished_at else None,
            listings_planned=report.listings_planned,
            pages_fetched=report.pages_fetched,
            observations_recorded=report.observations_recorded,
            prices_changed=report.prices_changed,
            observations_from_json_ld=report.extraction_sources[ExtractionSource.JSON_LD],
            observations_from_html_fallback=report.extraction_sources[
                ExtractionSource.HTML_FALLBACK
            ],
            stopped_early_because=report.stopped_early_because,
        )
        self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[tables.collection_runs.c.run_id],
                set_={
                    "finished_at": statement.excluded.finished_at,
                    "listings_planned": statement.excluded.listings_planned,
                    "pages_fetched": statement.excluded.pages_fetched,
                    "observations_recorded": statement.excluded.observations_recorded,
                    "prices_changed": statement.excluded.prices_changed,
                    "observations_from_json_ld": statement.excluded.observations_from_json_ld,
                    "observations_from_html_fallback": (
                        statement.excluded.observations_from_html_fallback
                    ),
                    "stopped_early_because": statement.excluded.stopped_early_because,
                },
            )
        )

        # As falhas são reescritas por inteiro para que uma segunda gravação do mesmo
        # relato não as duplique.
        self._connection.execute(
            delete(tables.collection_failures).where(
                tables.collection_failures.c.run_id == report.run_id
            )
        )
        if report.failures:
            self._connection.execute(
                tables.collection_failures.insert(),
                [
                    {
                        "failure_id": uuid4(),
                        "run_id": report.run_id,
                        "listing_id": failure.listing_id,
                        "url": failure.url,
                        "reason": failure.reason.value,
                        "detail": failure.detail,
                        "http_status": failure.http_status,
                    }
                    for failure in report.failures
                ],
            )

    def recent_for_store(self, slug: StoreSlug, limit: int = 30) -> Sequence[CollectionReport]:
        """Últimas passagens a esta loja, da mais recente para trás."""
        rows = (
            self._connection.execute(
                select(tables.collection_runs)
                .where(tables.collection_runs.c.store_slug == slug.value)
                .order_by(tables.collection_runs.c.started_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        if not rows:
            return []

        failures_by_run = self._failures_for({row["run_id"] for row in rows})
        return [
            CollectionReport(
                run_id=row["run_id"],
                store_slug=StoreSlug(row["store_slug"]),
                started_at=ObservedAt(row["started_at"]),
                finished_at=ObservedAt(row["finished_at"]) if row["finished_at"] else None,
                listings_planned=row["listings_planned"],
                pages_fetched=row["pages_fetched"],
                observations_recorded=row["observations_recorded"],
                prices_changed=row["prices_changed"],
                failures=failures_by_run.get(row["run_id"], []),
                extraction_sources=Counter(
                    {
                        ExtractionSource.JSON_LD: row["observations_from_json_ld"],
                        ExtractionSource.HTML_FALLBACK: row["observations_from_html_fallback"],
                    }
                ),
                stopped_early_because=row["stopped_early_because"],
            )
            for row in rows
        ]

    def _failures_for(self, run_ids: set[object]) -> dict[object, list[ObservedFailure]]:
        rows = self._connection.execute(
            select(tables.collection_failures).where(
                tables.collection_failures.c.run_id.in_(run_ids)
            )
        ).mappings()
        grouped: dict[object, list[ObservedFailure]] = {}
        for row in rows:
            grouped.setdefault(row["run_id"], []).append(
                ObservedFailure(
                    listing_id=row["listing_id"],
                    url=row["url"],
                    reason=FailureReason(row["reason"]),
                    detail=row["detail"],
                    http_status=row["http_status"],
                )
            )
        return grouped
