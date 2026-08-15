"""Repositórios contra PostgreSQL real, com as migrações aplicadas.

Nada aqui é mockado. A confiança de que o histórico é append-only e de que a passagem
diária é idempotente vem de correr contra a infraestrutura verdadeira — um duplo
concordaria com qualquer coisa que se lhe pedisse.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, text

from braunprices.domain.model.availability import Availability
from braunprices.domain.ports.repositories import (
    PriceObservationRepository,
    ProductRepository,
    StoreRepository,
)
from braunprices.domain.rules.price_reference import (
    ReferenceBasis,
    lowest_price_in_window,
    reference_price_for_announcement,
)
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.persistence.engine import unit_of_work
from braunprices.infrastructure.persistence.repositories import (
    SqlPriceObservationRepository,
    SqlProductRepository,
    SqlStoreRepository,
)
from tests.integration.factories import (
    OTHER_EAN,
    VALID_EAN,
    a_listing,
    a_product,
    a_store,
    an_observation,
)


@pytest.fixture
def stores(connection: Connection) -> SqlStoreRepository:
    return SqlStoreRepository(connection)


@pytest.fixture
def products(connection: Connection) -> SqlProductRepository:
    return SqlProductRepository(connection)


@pytest.fixture
def observations(connection: Connection) -> SqlPriceObservationRepository:
    return SqlPriceObservationRepository(connection)


# -- lojas -----------------------------------------------------------------


def test_a_store_survives_the_round_trip(stores: SqlStoreRepository) -> None:
    original = a_store()
    stores.add(original)
    assert stores.get(original.slug) == original


def test_an_unknown_store_is_none_and_not_an_error(stores: SqlStoreRepository) -> None:
    assert stores.get(StoreSlug("nao-existe")) is None


def test_stores_come_back_in_a_stable_order(stores: SqlStoreRepository) -> None:
    stores.add(a_store("zzz-loja"))
    stores.add(a_store("aaa-loja"))
    assert [store.slug.value for store in stores.list_all()] == ["aaa-loja", "zzz-loja"]


def test_the_database_refuses_a_rate_that_is_not_conservative(connection: Connection) -> None:
    # A mesma invariante do domínio, também na base de dados: uma inserção que
    # contorne a aplicação não deve conseguir configurar uma loja para ser martelada.
    with pytest.raises(Exception, match="requests_per_second_is_conservative"):
        connection.execute(
            text("INSERT INTO stores VALUES ('rapida', 'Rapida', 'rapida.pt', 50, 1, 20, 3, 2)")
        )


# -- produtos e referências ------------------------------------------------


def test_a_product_with_its_listings_survives_the_round_trip(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    stores.add(a_store("outra-loja"))
    original = a_product(
        listings=[a_listing("loja-exemplo", "111"), a_listing("outra-loja", "222")]
    )
    products.add(original)

    loaded = products.get(original.product_id)
    assert loaded is not None
    assert loaded.canonical_name == original.canonical_name
    assert loaded.ean == VALID_EAN
    assert {listing.external_id for listing in loaded.listings} == {"111", "222"}


def test_a_product_without_ean_is_stored_and_does_not_match_across_stores(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    original = a_product(ean=None, listings=[a_listing()])
    products.add(original)

    loaded = products.get(original.product_id)
    assert loaded is not None
    assert loaded.ean is None
    assert loaded.participates_in_cross_store_matching is False


def test_two_products_may_both_lack_an_ean(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    # A unicidade do EAN não pode transformar "sem EAN" num valor único: seriam
    # milhares de produtos a colidir uns com os outros.
    stores.add(a_store())
    products.add(a_product(ean=None, name="Um"))
    products.add(a_product(ean=None, name="Outro"))


def test_the_same_ean_cannot_belong_to_two_products(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    # O EAN é a chave de casamento entre lojas; dois produtos com o mesmo EAN seriam
    # o mesmo produto, e deixá-los coexistir partiria o casamento em silêncio.
    stores.add(a_store())
    products.add(a_product(ean=VALID_EAN, name="Um"))
    with pytest.raises(Exception, match="uq_products_ean"):
        products.add(a_product(ean=VALID_EAN, name="Outro"))


def test_finds_a_product_by_its_ean(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    original = a_product(ean=OTHER_EAN, listings=[a_listing()])
    products.add(original)

    found = products.get_by_ean(OTHER_EAN)
    assert found is not None
    assert found.product_id == original.product_id
    assert len(found.listings) == 1


def test_finds_the_product_a_listing_belongs_to(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    listing = a_listing()
    original = a_product(listings=[listing])
    products.add(original)

    found = products.get_by_listing(listing.listing_id)
    assert found is not None
    assert found.product_id == original.product_id


def test_an_unknown_listing_yields_no_product(products: SqlProductRepository) -> None:
    assert products.get_by_listing(uuid4()) is None


def test_the_same_external_id_cannot_repeat_within_a_store(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    products.add(a_product(name="Um", listings=[a_listing("loja-exemplo", "111")]))
    with pytest.raises(Exception, match="uq_store_listings_store_slug_external_id"):
        products.add(
            a_product(ean=OTHER_EAN, name="Outro", listings=[a_listing("loja-exemplo", "111")])
        )


def test_only_active_listings_are_offered_for_collection(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    active, to_deactivate = a_listing("loja-exemplo", "111"), a_listing("loja-exemplo", "222")
    original = a_product(listings=[active, to_deactivate])
    products.add(original)

    original.deactivate_listing(to_deactivate.listing_id)
    products.save(original)

    remaining = products.active_listings_for_store(StoreSlug("loja-exemplo"))
    assert [listing.external_id for listing in remaining] == ["111"]


def test_deactivating_a_listing_keeps_it_in_the_database(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    # A referência inativa deixa de ser visitada, não deixa de ter passado: as
    # observações já recolhidas continuam a apontar para ela.
    stores.add(a_store())
    listing = a_listing()
    original = a_product(listings=[listing])
    products.add(original)

    original.deactivate_listing(listing.listing_id)
    products.save(original)

    loaded = products.get(original.product_id)
    assert loaded is not None
    assert len(loaded.listings) == 1
    assert loaded.listing(listing.listing_id).is_active is False


def test_saving_a_product_can_add_a_listing_in_another_store(
    stores: SqlStoreRepository, products: SqlProductRepository
) -> None:
    stores.add(a_store())
    stores.add(a_store("outra-loja"))
    original = a_product(listings=[a_listing("loja-exemplo", "111")])
    products.add(original)

    original.add_listing(a_listing("outra-loja", "999"))
    products.save(original)

    loaded = products.get(original.product_id)
    assert loaded is not None
    assert len(loaded.listings) == 2


# -- observações de preço --------------------------------------------------


def test_observations_survive_the_round_trip(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))

    original = an_observation(listing, day="2026-07-01", price="1299.99")
    assert observations.add_all([original]) == 1

    stored = observations.history_for_listing(listing.listing_id)
    assert len(stored) == 1
    assert stored[0] == original


def test_the_decimal_scale_comes_back_as_the_currency_defines_it(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    # A coluna é NUMERIC(14, 4) e devolveria 59.9900; o montante tem de voltar com a
    # escala do euro, ou deixaria de ser igual ao que se gravou.
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all([an_observation(listing, price="59.99")])

    stored = observations.history_for_listing(listing.listing_id)
    assert stored[0].price == Money.of("59.99")
    assert stored[0].price.amount == Decimal("59.99")


def test_running_the_same_collection_twice_does_not_duplicate(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    # Idempotência da passagem diária: o mesmo facto observado duas vezes no mesmo dia
    # é um facto, não dois.
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))

    first = an_observation(listing, day="2026-07-01", hour=9, price="59.99")
    second = an_observation(listing, day="2026-07-01", hour=18, price="59.99")

    assert observations.add_all([first]) == 1
    assert observations.add_all([second]) == 0
    assert len(observations.history_for_listing(listing.listing_id)) == 1


def test_a_price_change_within_the_same_day_is_a_new_fact(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))

    observations.add_all([an_observation(listing, day="2026-07-01", hour=9, price="59.99")])
    assert (
        observations.add_all([an_observation(listing, day="2026-07-01", hour=18, price="49.99")])
        == 1
    )
    assert len(observations.observed_on(listing.listing_id, date(2026, 7, 1))) == 2


def test_an_availability_change_is_also_a_new_fact(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))

    observations.add_all([an_observation(listing, day="2026-07-01", price="59.99")])
    assert (
        observations.add_all(
            [
                an_observation(
                    listing,
                    day="2026-07-01",
                    hour=18,
                    price="59.99",
                    availability=Availability.OUT_OF_STOCK,
                )
            ]
        )
        == 1
    )


def test_adding_nothing_writes_nothing(observations: SqlPriceObservationRepository) -> None:
    assert observations.add_all([]) == 0


def test_history_comes_back_in_chronological_order(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all(
        [
            an_observation(listing, day="2026-07-03", price="70.00"),
            an_observation(listing, day="2026-07-01", price="90.00"),
            an_observation(listing, day="2026-07-02", price="80.00"),
        ]
    )

    stored = observations.history_for_listing(listing.listing_id)
    assert [item.price.amount for item in stored] == [
        Decimal("90.00"),
        Decimal("80.00"),
        Decimal("70.00"),
    ]


def test_history_can_be_bounded_by_lisbon_days(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all(
        [
            an_observation(listing, day=f"2026-07-{day:02d}", price=f"{day}0.00")
            for day in range(1, 6)
        ]
    )

    bounded = observations.history_for_listing(
        listing.listing_id, since=date(2026, 7, 2), until=date(2026, 7, 4)
    )
    assert [item.local_date.day for item in bounded] == [2, 3, 4]


def test_the_latest_observation_is_the_most_recent_instant(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all(
        [
            an_observation(listing, day="2026-07-01", price="90.00"),
            an_observation(listing, day="2026-07-05", price="70.00"),
        ]
    )

    latest = observations.latest_for_listing(listing.listing_id)
    assert latest is not None
    assert latest.price == Money.of("70.00")


def test_a_listing_without_history_has_no_latest(
    observations: SqlPriceObservationRepository,
) -> None:
    assert observations.latest_for_listing(uuid4()) is None


def test_an_observation_cannot_point_at_a_listing_that_does_not_exist(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    stores.add(a_store())
    orphan = a_listing()
    with pytest.raises(Exception, match="fk_price_observations_listing_id_store_listings"):
        observations.add_all([an_observation(orphan)])


# -- o dia de Lisboa gravado concorda com o domínio -------------------------


def test_the_stored_day_follows_lisbon_and_not_utc(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
    connection: Connection,
) -> None:
    # 23:30 de 12/07 em Lisboa é 22:30 UTC. Se `observed_day` fosse derivado do
    # instante em UTC por engano, a observação cairia no dia errado e a janela de 30
    # dias deslocava-se com ela.
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all([an_observation(listing, day="2026-07-12", hour=23, price="59.99")])

    stored_day = connection.execute(
        text("SELECT observed_day FROM price_observations LIMIT 1")
    ).scalar_one()
    assert stored_day == date(2026, 7, 12)


def test_the_stored_day_always_matches_what_the_domain_computes(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
    connection: Connection,
) -> None:
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    written = [
        an_observation(listing, day="2026-03-29", hour=1, price="10.00"),  # avanço do relógio
        an_observation(listing, day="2026-10-25", hour=1, price="20.00"),  # recuo do relógio
        an_observation(listing, day="2026-12-31", hour=23, price="30.00"),  # fim de ano
    ]
    observations.add_all(written)

    rows = connection.execute(
        text("SELECT observed_day FROM price_observations ORDER BY observed_at")
    ).scalars()
    assert list(rows) == [item.local_date for item in written]


# -- a regra dos 30 dias ponta a ponta -------------------------------------


def test_the_thirty_day_rule_works_over_data_read_back_from_postgres(
    stores: SqlStoreRepository,
    products: SqlProductRepository,
    observations: SqlPriceObservationRepository,
) -> None:
    # O ponto deste teste não é a regra — essa tem testes de unidade — mas provar que
    # o que sai da base de dados é aceite pelo domínio sem qualquer adaptação.
    stores.add(a_store())
    listing = a_listing()
    products.add(a_product(listings=[listing]))
    observations.add_all(
        [
            an_observation(listing, day="2026-06-15", price="100.00"),
            an_observation(listing, day="2026-06-22", price="90.00"),
            an_observation(listing, day="2026-06-29", price="80.00"),
            an_observation(listing, day="2026-07-06", price="70.00"),
        ]
    )

    history = observations.history_for_listing(listing.listing_id)
    assert lowest_price_in_window(history, date(2026, 7, 12)) == Money.of("70.00")

    reference = reference_price_for_announcement(history, date(2026, 7, 12))
    assert reference is not None
    assert reference.price == Money.of("100.00")
    assert reference.basis is ReferenceBasis.BEFORE_PROGRESSIVE_REDUCTION


# -- conformidade com os portos do domínio ---------------------------------


def test_the_sql_repositories_satisfy_the_ports_the_domain_declares(
    connection: Connection,
) -> None:
    # A conformidade é estrutural: nenhuma destas classes herda dos Protocol. Quem a
    # verifica de facto é o mypy, sobre estas anotações; o teste garante que as
    # classes ao menos instanciam, para que a anotação não fique a falar de um tipo
    # que já ninguém consegue construir.
    stores: StoreRepository = SqlStoreRepository(connection)
    products: ProductRepository = SqlProductRepository(connection)
    observations: PriceObservationRepository = SqlPriceObservationRepository(connection)
    assert stores.get(StoreSlug("nao-existe")) is None
    assert products.get(uuid4()) is None
    assert observations.latest_for_listing(uuid4()) is None


def test_a_unit_of_work_commits_what_happens_inside_it(migrated_engine: Engine) -> None:
    with unit_of_work(migrated_engine) as work:
        SqlStoreRepository(work).add(a_store("transacional"))

    with migrated_engine.connect() as verification:
        assert SqlStoreRepository(verification).get(StoreSlug("transacional")) is not None

    with migrated_engine.begin() as cleanup:
        cleanup.execute(text("DELETE FROM stores WHERE slug = 'transacional'"))


def test_a_unit_of_work_rolls_back_everything_when_it_fails(migrated_engine: Engine) -> None:
    # Uma passagem de recolha que rebente a meio não pode deixar metade dos produtos
    # gravados: seria um estado que ninguém observou.
    def a_pass_that_fails_midway() -> None:
        with unit_of_work(migrated_engine) as work:
            SqlStoreRepository(work).add(a_store("efemera"))
            message = "falha a meio da passagem"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="falha a meio"):
        a_pass_that_fails_midway()

    with migrated_engine.connect() as verification:
        assert SqlStoreRepository(verification).get(StoreSlug("efemera")) is None
