"""A CLI, contra a base de dados real.

É por aqui que a recolha é disparada em produção, por cron. Um erro aqui não dá erro
de tipos nem falha de importação: dá um dia sem histórico, e esse não se recupera.

O único ponto substituído é o adaptador de loja, para que nenhum teste toque na rede.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from braunprices.domain.model.scrape_outcome import FailureReason, ScrapeFailure
from braunprices.domain.model.store import Store
from braunprices.infrastructure import composition
from braunprices.infrastructure.config import get_settings
from braunprices.infrastructure.scraping.http_client import CollectionHttpClient
from braunprices.interfaces.cli.main import app
from tests.integration.test_collect_store_prices import STORE, ScriptedScraper

runner = CliRunner()


@pytest.fixture(autouse=True)
def settings_from_the_container(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Faz a CLI apontar ao Postgres do container e limpa a base no fim.

    ``migrated_engine`` já deixa ``BRAUNPRICES_DATABASE_URL`` no ambiente; falta
    invalidar a cache das definições, que de outra forma guardaria as do processo.

    O engine é partilhado com a suite em vez de ser criado a cada invocação. Num
    processo real a CLI corre um comando e sai, e o pool morre com ele; aqui morreriam
    dezenas de pools por sessão, e as ligações por fechar apareceriam como avisos que
    nada têm a ver com o que está sob teste.
    """
    get_settings.cache_clear()
    monkeypatch.setattr(composition, "build_engine", lambda _url: migrated_engine)
    yield
    get_settings.cache_clear()
    with migrated_engine.begin() as cleanup:
        cleanup.execute(
            text(
                "TRUNCATE collection_failures, collection_runs, price_observations, "
                "store_listings, products, stores RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def offline_scraper(monkeypatch: pytest.MonkeyPatch) -> ScriptedScraper:
    """Regista um adaptador para `loja-exemplo` que nunca sai do processo."""
    scraper = ScriptedScraper()

    def build(store: Store, http_client: CollectionHttpClient) -> ScriptedScraper:
        return scraper

    monkeypatch.setitem(composition.SCRAPERS, STORE, build)
    return scraper


def register_store(slug: str = "loja-exemplo") -> None:
    result = runner.invoke(
        app,
        ["lojas", "registar", slug, "--nome", f"Loja {slug}", "--dominio", f"{slug}.pt"],
    )
    assert result.exit_code == 0, result.stdout


def add_listing(slug: str = "loja-exemplo", external_id: str = "1") -> None:
    result = runner.invoke(
        app,
        [
            "referencias",
            "adicionar",
            slug,
            f"https://{slug}.pt/p/{external_id}",
            "--referencia",
            external_id,
            "--nome",
            f"Produto {external_id}",
        ],
    )
    assert result.exit_code == 0, result.stdout


# -- configuração ----------------------------------------------------------


def test_registering_a_store_and_listing_it_back() -> None:
    register_store()
    result = runner.invoke(app, ["lojas", "listar"])
    assert result.exit_code == 0
    assert "loja-exemplo" in result.stdout
    assert "0.5 pedidos/s" in result.stdout


def test_registering_the_same_store_twice_is_refused() -> None:
    register_store()
    result = runner.invoke(
        app, ["lojas", "registar", "loja-exemplo", "--nome", "X", "--dominio", "x.pt"]
    )
    assert result.exit_code == 1
    assert "já está registada" in result.stdout


def test_listing_stores_when_there_are_none() -> None:
    result = runner.invoke(app, ["lojas", "listar"])
    assert result.exit_code == 0
    assert "Sem lojas registadas" in result.stdout


def test_a_listing_needs_its_store_to_exist_first() -> None:
    result = runner.invoke(
        app,
        [
            "referencias",
            "adicionar",
            "loja-fantasma",
            "https://loja-fantasma.pt/p/1",
            "--referencia",
            "1",
            "--nome",
            "Produto",
        ],
    )
    assert result.exit_code == 1
    assert "não está registada" in result.stdout


def test_a_second_listing_with_the_same_ean_joins_the_product_that_already_exists() -> None:
    # É assim que o casamento entre lojas acontece — e é o que torna comparável o
    # histórico do mesmo produto em duas lojas.
    register_store("loja-a")
    register_store("loja-b")
    outputs = []
    for slug in ("loja-a", "loja-b"):
        result = runner.invoke(
            app,
            [
                "referencias",
                "adicionar",
                slug,
                f"https://{slug}.pt/p/1",
                "--referencia",
                "1",
                "--nome",
                "Máquina de café",
                "--ean",
                "4006381333931",
            ],
        )
        assert result.exit_code == 0, result.stdout
        outputs.append(result.stdout)

    assert "Produto e referência criados" in outputs[0]
    assert "ligada ao produto que já existia" in outputs[1]


# -- recolha ---------------------------------------------------------------


def test_collecting_from_a_store_that_is_not_registered_says_so(
    offline_scraper: ScriptedScraper,
) -> None:
    result = runner.invoke(app, ["recolher", "loja-exemplo"])
    assert result.exit_code == 1
    assert "não está registada" in result.stdout
    assert offline_scraper.visited == []


def test_a_clean_pass_exits_zero_and_prints_what_happened(
    offline_scraper: ScriptedScraper,
) -> None:
    register_store()
    add_listing()

    result = runner.invoke(app, ["recolher", "loja-exemplo"])

    assert result.exit_code == 0, result.stdout
    assert offline_scraper.visited == ["1"]
    assert "1/1 páginas" in result.stdout
    assert "1 observações novas" in result.stdout


def test_a_pass_worth_investigating_exits_with_a_code_the_scheduler_notices(
    offline_scraper: ScriptedScraper,
) -> None:
    # Sem isto, um cron a apanhar um bloqueio da loja continuaria a devolver sucesso e
    # ninguém daria por nada até faltar histórico.
    register_store()
    add_listing()
    offline_scraper.outcomes["1"] = ScrapeFailure(
        reason=FailureReason.BLOCKED,
        detail="A loja respondeu 429.",
        http_status=429,
    )

    result = runner.invoke(app, ["recolher", "loja-exemplo"])

    assert result.exit_code == 2
    assert "parou cedo" in result.stdout
    assert "merece ser investigada" in result.stdout


def test_the_limit_option_reaches_the_use_case(offline_scraper: ScriptedScraper) -> None:
    register_store()
    add_listing(external_id="1")
    add_listing(external_id="2")

    result = runner.invoke(app, ["recolher", "loja-exemplo", "--limite", "1"])

    assert result.exit_code == 0, result.stdout
    assert offline_scraper.visited == ["1"]


def test_running_the_same_pass_twice_records_nothing_new(
    offline_scraper: ScriptedScraper,
) -> None:
    register_store()
    add_listing()
    runner.invoke(app, ["recolher", "loja-exemplo"])

    result = runner.invoke(app, ["recolher", "loja-exemplo"])

    assert result.exit_code == 0, result.stdout
    assert "0 observações novas" in result.stdout


# -- estado ----------------------------------------------------------------


def test_the_state_command_shows_the_passes_that_ran(offline_scraper: ScriptedScraper) -> None:
    register_store()
    add_listing()
    runner.invoke(app, ["recolher", "loja-exemplo"])

    result = runner.invoke(app, ["estado", "loja-exemplo"])

    assert result.exit_code == 0
    assert "[loja-exemplo]" in result.stdout
    assert "1/1 páginas" in result.stdout


def test_the_state_command_says_so_when_there_is_nothing_yet() -> None:
    result = runner.invoke(app, ["estado", "loja-exemplo"])
    assert result.exit_code == 0
    assert "Ainda não há passagens registadas" in result.stdout
