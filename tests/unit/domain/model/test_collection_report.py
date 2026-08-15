"""O relato de uma passagem: as contas que decidem se alguém tem de lhe pegar.

Estes números são o único mecanismo que o sistema tem para dar por uma degradação
silenciosa. Se estiverem errados, a recolha continua verde enquanto envenena o
histórico — que é a falha mais cara que este sistema pode ter.
"""

from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from braunprices.domain.model.collection_run import CollectionReport, ObservedFailure
from braunprices.domain.model.scrape_outcome import ExtractionSource, FailureReason
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug

STARTED = ObservedAt(datetime(2026, 8, 15, 3, 0, tzinfo=UTC))


def a_report(**overrides: object) -> CollectionReport:
    values: dict[str, object] = {
        "run_id": uuid4(),
        "store_slug": StoreSlug("loja-exemplo"),
        "started_at": STARTED,
    }
    values.update(overrides)
    return CollectionReport(**values)  # type: ignore[arg-type]


def a_failure(reason: FailureReason = FailureReason.MARKUP_MISSING) -> ObservedFailure:
    return ObservedFailure(
        listing_id=uuid4(),
        url="https://loja-exemplo.pt/p/1",
        reason=reason,
        detail="detalhe para quem vier investigar",
    )


def test_attempts_are_pages_plus_failures() -> None:
    report = a_report(pages_fetched=8, failures=[a_failure(), a_failure()])
    assert report.listings_attempted == 10


def test_the_success_rate_is_the_fraction_that_produced_an_observation() -> None:
    report = a_report(pages_fetched=9, failures=[a_failure()])
    assert report.success_rate == pytest.approx(0.9)


def test_a_pass_with_nothing_to_do_did_not_fail() -> None:
    # Zero tentativas não é zero por cento de sucesso: é uma loja sem referências
    # ativas, que não tem nada de errado.
    assert a_report().success_rate == 1.0
    assert a_report().is_worth_investigating is False


def test_failures_are_counted_by_reason() -> None:
    report = a_report(
        failures=[
            a_failure(FailureReason.TIMEOUT),
            a_failure(FailureReason.TIMEOUT),
            a_failure(FailureReason.MARKUP_MISSING),
        ]
    )
    assert report.failures_by_reason == {
        FailureReason.TIMEOUT: 2,
        FailureReason.MARKUP_MISSING: 1,
    }


def test_the_fallback_rate_is_the_fraction_that_came_from_the_html() -> None:
    report = a_report(
        extraction_sources=Counter(
            {ExtractionSource.JSON_LD: 90, ExtractionSource.HTML_FALLBACK: 10}
        )
    )
    assert report.fallback_rate == pytest.approx(0.1)


def test_without_observations_the_fallback_rate_is_zero_and_not_an_error() -> None:
    assert a_report().fallback_rate == 0.0


@pytest.mark.parametrize(
    "reason",
    [FailureReason.BLOCKED, FailureReason.DISALLOWED_BY_ROBOTS],
)
def test_a_refusal_from_the_store_marks_the_pass_as_blocked(reason: FailureReason) -> None:
    report = a_report(pages_fetched=999, failures=[a_failure(reason)])
    assert report.was_blocked is True
    # E manda investigar mesmo com a taxa de sucesso quase perfeita: uma recusa não se
    # dilui em volume.
    assert report.success_rate > 0.95
    assert report.is_worth_investigating is True


def test_markup_that_changed_is_not_the_store_saying_no() -> None:
    # A distinção decide o que fazer a seguir: perante recusa, para-se; perante
    # marcação mudada, há manutenção a fazer no adaptador.
    report = a_report(pages_fetched=99, failures=[a_failure(FailureReason.MARKUP_MISSING)])
    assert report.was_blocked is False


def test_a_success_rate_below_the_threshold_is_worth_investigating() -> None:
    report = a_report(pages_fetched=94, failures=[a_failure() for _ in range(6)])
    assert report.success_rate < 0.95
    assert report.is_worth_investigating is True


def test_too_much_recourse_to_the_html_is_worth_investigating() -> None:
    # A loja continua a devolver preços. É precisamente por isso que sem este número
    # ninguém daria por nada.
    report = a_report(
        pages_fetched=100,
        extraction_sources=Counter(
            {ExtractionSource.JSON_LD: 80, ExtractionSource.HTML_FALLBACK: 20}
        ),
    )
    assert report.success_rate == 1.0
    assert report.fallback_rate > 0.10
    assert report.is_worth_investigating is True


def test_a_clean_pass_is_left_alone() -> None:
    report = a_report(
        pages_fetched=100,
        extraction_sources=Counter({ExtractionSource.JSON_LD: 100}),
    )
    assert report.is_worth_investigating is False
