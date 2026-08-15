"""A API pública, contra Postgres real.

Sem duplos: o que está sob teste é a resposta que um terceiro recebe, e um duplo
concordaria com qualquer forma que se lhe pedisse. A base de dados é a mesma dos outros
testes de integração, com as migrações aplicadas.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import StoreListing
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure import composition
from braunprices.infrastructure.config import Settings
from braunprices.infrastructure.persistence.engine import build_engine
from braunprices.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from braunprices.interfaces.api.app import create_app
from braunprices.interfaces.api.public.router import CACHE_SECONDS
from tests.integration.factories import VALID_EAN, a_listing, a_product, a_store

STORE = StoreSlug("loja-exemplo")


def an_observation_at(
    listing: StoreListing,
    day: int,
    price: str,
    *,
    availability: Availability = Availability.IN_STOCK,
    hour: int = 9,
) -> PriceObservation:
    """Observação num dia de julho de 2026, à hora indicada."""
    return PriceObservation(
        listing_id=listing.listing_id,
        store_slug=listing.store_slug,
        observed_at=ObservedAt(datetime(2026, 7, day, hour, tzinfo=UTC)),
        price=Money.of(Decimal(price)),
        availability=availability,
        source_url=listing.url,
        raw_hash=f"sha256:{day}-{hour}-{price}",
    )


@pytest.fixture
def listing(migrated_engine: Engine) -> Iterator[StoreListing]:
    """Uma loja com uma referência e histórico de julho, limpa no fim."""
    prepared = a_listing("loja-exemplo", "5513302")
    with SqlUnitOfWork(migrated_engine) as work:
        work.stores.add(a_store())
        work.products.add(a_product(name="Tinteiro HP 971", listings=[prepared]))
        work.observations.add_all(
            [
                an_observation_at(prepared, 1, "99.67"),
                an_observation_at(prepared, 2, "99.67"),
                an_observation_at(prepared, 3, "89.90"),
                an_observation_at(prepared, 4, "89.90", availability=Availability.OUT_OF_STOCK),
                an_observation_at(prepared, 5, "79.90"),
            ]
        )
        work.commit()
    yield prepared
    with migrated_engine.begin() as cleanup:
        cleanup.execute(
            text(
                "TRUNCATE collection_failures, collection_runs, price_observations, "
                "store_listings, products, stores RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def client(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Cliente sobre a aplicação real, ligada ao Postgres do container."""
    monkeypatch.setattr(composition, "build_engine", lambda _url: migrated_engine)
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


# -- lojas -----------------------------------------------------------------


def test_stores_are_listed_with_the_pace_they_are_visited_at(
    client: TestClient, listing: StoreListing
) -> None:
    # O ritmo é público de propósito: quem é responsável por um dos sites vê a que
    # ritmo está a ser visitado sem ter de perguntar a ninguém.
    response = client.get("/api/v1/lojas")

    assert response.status_code == 200
    assert response.json() == [
        {
            "slug": "loja-exemplo",
            "nome": "Loja loja-exemplo",
            "dominio": "loja-exemplo.pt",
            "pedidos_por_segundo": 0.5,
        }
    ]


# -- produtos --------------------------------------------------------------


def test_a_product_carries_its_listings_and_the_latest_observation(
    client: TestClient, listing: StoreListing, migrated_engine: Engine
) -> None:
    with SqlUnitOfWork(migrated_engine) as work:
        product = work.products.get_by_listing(listing.listing_id)
    assert product is not None

    body = client.get(f"/api/v1/produtos/{product.product_id}").json()

    assert body["nome"] == "Tinteiro HP 971"
    assert body["ean"] == VALID_EAN.value
    assert len(body["referencias"]) == 1
    reference = body["referencias"][0]
    assert reference["loja"] == "loja-exemplo"
    assert reference["referencia_na_loja"] == "5513302"
    assert reference["ultima_observacao"]["preco"] == {"montante": "79.90", "moeda": "EUR"}


def test_an_unknown_product_is_a_404_that_says_what_was_looked_for(client: TestClient) -> None:
    response = client.get(f"/api/v1/produtos/{uuid4()}")
    assert response.status_code == 404
    assert "Não há produto" in response.json()["detail"]


def test_a_product_can_be_found_by_ean(client: TestClient, listing: StoreListing) -> None:
    response = client.get("/api/v1/produtos", params={"ean": VALID_EAN.value})
    assert response.status_code == 200
    assert response.json()["ean"] == VALID_EAN.value


def test_an_ean_that_fails_the_checksum_is_a_400_and_not_a_404(client: TestClient) -> None:
    # A distinção interessa a quem chama: 404 diria "não temos esse produto" quando o
    # que aconteceu foi "esse código não é um EAN".
    response = client.get("/api/v1/produtos", params={"ean": "4006381333930"})
    assert response.status_code == 400
    assert "dígito de controlo" in response.json()["detail"].lower()


def test_an_ean_nobody_observed_is_a_404(client: TestClient, listing: StoreListing) -> None:
    response = client.get("/api/v1/produtos", params={"ean": "5449000000996"})
    assert response.status_code == 404


# -- histórico -------------------------------------------------------------


def test_the_history_comes_back_oldest_first_with_provenance(
    client: TestClient, listing: StoreListing
) -> None:
    body = client.get(f"/api/v1/referencias/{listing.listing_id}/historico").json()

    assert body["produto"] == "Tinteiro HP 971"
    assert [item["dia"] for item in body["observacoes"]] == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-04",
        "2026-07-05",
    ]
    first = body["observacoes"][0]
    assert first["url"] == listing.url
    assert first["impressao_do_conteudo"].startswith("sha256:")
    assert body["cursor_seguinte"] is None


def test_money_travels_as_decimal_text_and_never_as_a_number(
    client: TestClient, listing: StoreListing
) -> None:
    # Um cêntimo perdido num arredondamento de vírgula flutuante é um facto errado
    # publicado sobre uma empresa identificada.
    raw = client.get(f"/api/v1/referencias/{listing.listing_id}/historico").text
    assert '"montante":"99.67"' in raw.replace(" ", "")
    assert '"montante":99.67' not in raw.replace(" ", "")


def test_an_out_of_stock_observation_is_published_and_marked_as_not_practised(
    client: TestClient, listing: StoreListing
) -> None:
    body = client.get(f"/api/v1/referencias/{listing.listing_id}/historico").json()
    day_four = next(item for item in body["observacoes"] if item["dia"] == "2026-07-04")
    assert day_four["disponibilidade"] == "out_of_stock"
    assert day_four["conta_como_preco_praticado"] is False


def test_the_history_can_be_bounded_by_lisbon_days(
    client: TestClient, listing: StoreListing
) -> None:
    body = client.get(
        f"/api/v1/referencias/{listing.listing_id}/historico",
        params={"desde": "2026-07-02", "ate": "2026-07-03"},
    ).json()
    assert [item["dia"] for item in body["observacoes"]] == ["2026-07-02", "2026-07-03"]


def test_an_inverted_interval_is_refused_instead_of_answered_with_nothing(
    client: TestClient, listing: StoreListing
) -> None:
    response = client.get(
        f"/api/v1/referencias/{listing.listing_id}/historico",
        params={"desde": "2026-07-05", "ate": "2026-07-01"},
    )
    assert response.status_code == 400
    assert "invertido" in response.json()["detail"]


def test_the_history_of_an_unknown_listing_is_a_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/referencias/{uuid4()}/historico")
    assert response.status_code == 404


def test_paging_walks_the_whole_history_without_repeating_or_skipping(
    client: TestClient, listing: StoreListing
) -> None:
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # teto de segurança; a série tem 5 factos e páginas de 2
        params: dict[str, str | int] = {"limite": 2}
        if cursor is not None:
            params["cursor"] = cursor
        body = client.get(
            f"/api/v1/referencias/{listing.listing_id}/historico", params=params
        ).json()
        seen.extend(item["dia"] for item in body["observacoes"])
        cursor = body["cursor_seguinte"]
        if cursor is None:
            break

    assert seen == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
        "2026-07-04",
        "2026-07-05",
    ]
    assert len(seen) == len(set(seen))


def test_a_fact_written_between_pages_does_not_shift_the_ones_already_read(
    client: TestClient, listing: StoreListing, migrated_engine: Engine
) -> None:
    # É a razão de o cursor ser o último facto lido e não um deslocamento: com OFFSET,
    # um facto novo no início da série empurraria a página seguinte e o leitor receberia
    # uma observação repetida sem nada lhe dizer que isso aconteceu.
    first = client.get(
        f"/api/v1/referencias/{listing.listing_id}/historico", params={"limite": 2}
    ).json()
    assert [item["dia"] for item in first["observacoes"]] == ["2026-07-01", "2026-07-02"]

    with SqlUnitOfWork(migrated_engine) as work:
        work.observations.add_all([an_observation_at(listing, 1, "97.00", hour=6)])
        work.commit()

    second = client.get(
        f"/api/v1/referencias/{listing.listing_id}/historico",
        params={"limite": 2, "cursor": first["cursor_seguinte"]},
    ).json()
    assert [item["dia"] for item in second["observacoes"]] == ["2026-07-03", "2026-07-04"]


def test_a_cursor_that_is_not_readable_is_refused_and_not_answered_with_page_one(
    client: TestClient, listing: StoreListing
) -> None:
    response = client.get(
        f"/api/v1/referencias/{listing.listing_id}/historico",
        params={"cursor": "isto-nao-e-um-cursor"},
    )
    assert response.status_code == 400
    assert "cursor" in response.json()["detail"].lower()


def test_a_page_larger_than_the_ceiling_is_refused_by_the_contract(
    client: TestClient, listing: StoreListing
) -> None:
    response = client.get(
        f"/api/v1/referencias/{listing.listing_id}/historico", params={"limite": 5000}
    )
    assert response.status_code == 422


# -- preço de referência ---------------------------------------------------


def test_the_reference_price_answers_the_question_the_project_exists_for(
    client: TestClient, listing: StoreListing
) -> None:
    body = client.get(
        f"/api/v1/referencias/{listing.listing_id}/preco-de-referencia",
        params={"data": "2026-07-20"},
    ).json()

    assert body["janela"] == {
        "inicio": "2026-06-20",
        "fim_exclusivo": "2026-07-20",
        "dias": 30,
    }
    # A série elegível desce sem interrupção — 99,67 → 89,90 → 79,90 — e o dia esgotado
    # não a interrompe porque não conta como preço praticado. Aplica-se o n.º 5 do
    # artigo: a referência é o preço antes da primeira redução, e não o mínimo atingido.
    assert body["preco_de_referencia"] == {"montante": "99.67", "moeda": "EUR"}
    assert body["base_da_referencia"] == "before_progressive_reduction"
    assert body["mais_baixo_na_janela"] == {"montante": "79.90", "moeda": "EUR"}
    assert body["ha_historico_suficiente"] is True


def test_the_out_of_stock_day_does_not_enter_the_count(
    client: TestClient, listing: StoreListing
) -> None:
    body = client.get(
        f"/api/v1/referencias/{listing.listing_id}/preco-de-referencia",
        params={"data": "2026-07-20"},
    ).json()
    assert body["observacoes_consideradas"] == 4  # cinco factos, um esgotado


def test_a_window_without_observations_says_it_does_not_know(
    client: TestClient, listing: StoreListing
) -> None:
    # Não se responde zero nem se estima. Um produto sobre o qual não há dados não
    # esteve a custar nada.
    body = client.get(
        f"/api/v1/referencias/{listing.listing_id}/preco-de-referencia",
        params={"data": "2026-01-15"},
    ).json()

    assert body["preco_de_referencia"] is None
    assert body["base_da_referencia"] is None
    assert body["mais_baixo_na_janela"] is None
    assert body["observacoes_consideradas"] == 0
    assert body["ha_historico_suficiente"] is False


def test_the_window_can_be_asked_for_a_different_number_of_days(
    client: TestClient, listing: StoreListing
) -> None:
    body = client.get(
        f"/api/v1/referencias/{listing.listing_id}/preco-de-referencia",
        params={"data": "2026-07-04", "dias": 2},
    ).json()
    assert body["janela"] == {"inicio": "2026-07-02", "fim_exclusivo": "2026-07-04", "dias": 2}
    assert body["mais_baixo_na_janela"] == {"montante": "89.90", "moeda": "EUR"}


def test_the_reference_price_of_an_unknown_listing_is_a_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/referencias/{uuid4()}/preco-de-referencia")
    assert response.status_code == 404


def test_a_price_that_went_back_up_falls_under_the_general_rule(
    client: TestClient, listing: StoreListing, migrated_engine: Engine
) -> None:
    # Uma subida no meio significa que o preço foi reposto e que a campanha não é
    # contínua. Aí volta a valer a regra geral, e a referência é o mínimo da janela.
    other = a_listing("loja-exemplo", "campanha")
    with SqlUnitOfWork(migrated_engine) as work:
        product = work.products.get_by_listing(listing.listing_id)
        assert product is not None
        product.add_listing(other)
        work.products.save(product)
        work.observations.add_all(
            [
                an_observation_at(other, 1, "100.00"),
                an_observation_at(other, 2, "90.00"),
                an_observation_at(other, 3, "100.00"),
                an_observation_at(other, 4, "80.00"),
            ]
        )
        work.commit()

    body = client.get(
        f"/api/v1/referencias/{other.listing_id}/preco-de-referencia",
        params={"data": "2026-07-05"},
    ).json()

    assert body["base_da_referencia"] == "lowest_in_window"
    assert body["preco_de_referencia"] == {"montante": "80.00", "moeda": "EUR"}
    assert body["mais_baixo_na_janela"] == {"montante": "80.00", "moeda": "EUR"}


# -- cabeçalhos e operação -------------------------------------------------


def test_read_responses_may_be_cached(client: TestClient, listing: StoreListing) -> None:
    response = client.get(f"/api/v1/referencias/{listing.listing_id}/historico")
    assert response.headers["cache-control"] == f"public, max-age={CACHE_SECONDS}"
    assert response.headers["last-modified"].endswith("GMT")


def test_health_says_the_database_answers(client: TestClient) -> None:
    body = client.get("/saude").json()
    assert body["base_de_dados"] is True
    assert body["versao"]


def test_health_says_so_when_the_database_does_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Um `/saude` que responde bem com a base de dados em baixo é pior do que não ter
    # `/saude` nenhum: a supervisão fica descansada exatamente quando não devia.
    unreachable = build_engine("postgresql+psycopg://ninguem:ninguem@127.0.0.1:1/nada")
    monkeypatch.setattr(composition, "build_engine", lambda _url: unreachable)
    with TestClient(create_app(Settings())) as broken:
        body = broken.get("/saude").json()
    assert body["base_de_dados"] is False
    assert body["versao"]


def test_the_public_surface_has_no_write_path(client: TestClient) -> None:
    # A superfície de escrita é outra, com outro prefixo e outra autenticação. Um
    # engano de encaminhamento que trouxesse escrita para aqui é apanhado por isto.
    paths = client.get("/openapi.json").json()["paths"]
    methods = {method.upper() for operations in paths.values() for method in operations}
    assert methods == {"GET"}


def test_the_documented_contract_describes_the_law_it_implements(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert "109-G/2021" in spec["info"]["description"]
    assert spec["info"]["license"]["identifier"] == "AGPL-3.0-or-later"
