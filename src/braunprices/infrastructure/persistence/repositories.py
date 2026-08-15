"""Implementações dos portos de persistência, sobre uma ``Connection`` do SQLAlchemy.

Cada repositório recebe a ligação de fora e não gere transações: quem decide o que é
uma unidade de trabalho é o caso de uso, não o armazenamento.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import Connection, delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import Store
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.persistence import tables
from braunprices.infrastructure.persistence.mappers import (
    listing_to_row,
    observation_to_row,
    product_to_row,
    row_to_listing,
    row_to_observation,
    row_to_product,
    row_to_store,
    store_to_row,
)


class SqlStoreRepository:
    """Lojas configuradas, em PostgreSQL."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, store: Store) -> None:
        """Regista uma loja nova."""
        self._connection.execute(tables.stores.insert().values(**store_to_row(store)))

    def get(self, slug: StoreSlug) -> Store | None:
        """Devolve a loja com este slug, ou ``None`` se não existir."""
        row = (
            self._connection.execute(
                select(tables.stores).where(tables.stores.c.slug == slug.value)
            )
            .mappings()
            .one_or_none()
        )
        return row_to_store(row) if row is not None else None

    def list_all(self) -> Sequence[Store]:
        """Devolve todas as lojas configuradas, por slug."""
        rows = self._connection.execute(
            select(tables.stores).order_by(tables.stores.c.slug)
        ).mappings()
        return [row_to_store(row) for row in rows]


class SqlProductRepository:
    """Produtos e as suas referências em lojas, em PostgreSQL."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, product: Product) -> None:
        """Regista um produto novo com as referências que já tenha."""
        self._connection.execute(tables.products.insert().values(**product_to_row(product)))
        self._insert_listings(product)

    def save(self, product: Product) -> None:
        """Guarda alterações ao agregado: referências novas ou desativadas.

        Não toca em observações. Um produto muda; o que se observou dele não muda.
        """
        self._connection.execute(
            tables.products.update()
            .where(tables.products.c.product_id == product.product_id)
            .values(
                canonical_name=product.canonical_name,
                ean=product.ean.value if product.ean is not None else None,
            )
        )
        # As referências que saíram do agregado são removidas; as que ficaram são
        # reescritas. `is_active` é o único campo que muda na prática, e apagar uma
        # referência que tenha observações é travado pela chave estrangeira RESTRICT.
        known = {listing.listing_id for listing in product.listings}
        existing = self._connection.execute(
            select(tables.store_listings.c.listing_id).where(
                tables.store_listings.c.product_id == product.product_id
            )
        ).scalars()
        removed = [listing_id for listing_id in existing if listing_id not in known]
        if removed:
            self._connection.execute(
                delete(tables.store_listings).where(tables.store_listings.c.listing_id.in_(removed))
            )
        self._upsert_listings(product)

    def get(self, product_id: UUID) -> Product | None:
        """Devolve o produto com este identificador, com as referências carregadas."""
        row = (
            self._connection.execute(
                select(tables.products).where(tables.products.c.product_id == product_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return row_to_product(row, self._listings_of(product_id))

    def get_by_ean(self, ean: EAN) -> Product | None:
        """Devolve o produto com este EAN, a chave de casamento entre lojas."""
        row = (
            self._connection.execute(
                select(tables.products).where(tables.products.c.ean == ean.value)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return row_to_product(row, self._listings_of(row["product_id"]))

    def get_by_listing(self, listing_id: UUID) -> Product | None:
        """Devolve o produto a que esta referência de loja pertence."""
        product_id = self._connection.execute(
            select(tables.store_listings.c.product_id).where(
                tables.store_listings.c.listing_id == listing_id
            )
        ).scalar_one_or_none()
        return self.get(product_id) if product_id is not None else None

    def active_listings_for_store(self, slug: StoreSlug) -> Sequence[StoreListing]:
        """Referências a visitar na próxima passagem de recolha desta loja."""
        rows = self._connection.execute(
            select(tables.store_listings)
            .where(
                tables.store_listings.c.store_slug == slug.value,
                tables.store_listings.c.is_active.is_(True),
            )
            .order_by(tables.store_listings.c.external_id)
        ).mappings()
        return [row_to_listing(row) for row in rows]

    def _listings_of(self, product_id: UUID) -> list[StoreListing]:
        rows = self._connection.execute(
            select(tables.store_listings)
            .where(tables.store_listings.c.product_id == product_id)
            .order_by(tables.store_listings.c.store_slug, tables.store_listings.c.external_id)
        ).mappings()
        return [row_to_listing(row) for row in rows]

    def _insert_listings(self, product: Product) -> None:
        if not product.listings:
            return
        self._connection.execute(
            tables.store_listings.insert(),
            [listing_to_row(listing, product.product_id) for listing in product.listings],
        )

    def _upsert_listings(self, product: Product) -> None:
        for listing in product.listings:
            values = listing_to_row(listing, product.product_id)
            statement = postgres_insert(tables.store_listings).values(**values)
            self._connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[tables.store_listings.c.listing_id],
                    set_={
                        "external_id": statement.excluded.external_id,
                        "url": statement.excluded.url,
                        "is_active": statement.excluded.is_active,
                    },
                )
            )


class SqlPriceObservationRepository:
    """Histórico de observações, em PostgreSQL — **sem caminho de escrita destrutiva**.

    Não há aqui ``update`` nem ``delete``, e não é por esquecimento. A base de dados
    reforça a mesma regra com um trigger, para que nem uma sessão de ``psql`` a
    consiga contornar por engano.
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_all(self, observations: Iterable[PriceObservation]) -> int:
        """Acrescenta observações e devolve quantas ficaram de facto gravadas.

        Idempotente por facto diário: correr a recolha duas vezes no mesmo dia com o
        mesmo resultado não duplica. Se o preço mudou entre passagens, a chave difere
        e o facto novo entra — que é o que se quer registar.
        """
        rows = [observation_to_row(observation) for observation in observations]
        if not rows:
            return 0
        statement = (
            postgres_insert(tables.price_observations)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_price_observations_daily_fact")
            .returning(tables.price_observations.c.observation_id)
        )
        return len(self._connection.execute(statement).scalars().all())

    def history_for_listing(
        self,
        listing_id: UUID,
        since: date | None = None,
        until: date | None = None,
    ) -> Sequence[PriceObservation]:
        """Observações desta referência, por instante crescente.

        ``since`` e ``until`` são dias de Lisboa, ambos inclusivos.
        """
        query = select(tables.price_observations).where(
            tables.price_observations.c.listing_id == listing_id
        )
        if since is not None:
            query = query.where(tables.price_observations.c.observed_day >= since)
        if until is not None:
            query = query.where(tables.price_observations.c.observed_day <= until)
        rows = self._connection.execute(
            query.order_by(tables.price_observations.c.observed_at)
        ).mappings()
        return [row_to_observation(row) for row in rows]

    def latest_for_listing(self, listing_id: UUID) -> PriceObservation | None:
        """Última observação registada desta referência."""
        row = (
            self._connection.execute(
                select(tables.price_observations)
                .where(tables.price_observations.c.listing_id == listing_id)
                .order_by(tables.price_observations.c.observed_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return row_to_observation(row) if row is not None else None

    def observed_on(self, listing_id: UUID, day: date) -> Sequence[PriceObservation]:
        """Observações desta referência num dia de Lisboa."""
        rows = self._connection.execute(
            select(tables.price_observations)
            .where(
                tables.price_observations.c.listing_id == listing_id,
                tables.price_observations.c.observed_day == day,
            )
            .order_by(tables.price_observations.c.observed_at)
        ).mappings()
        return [row_to_observation(row) for row in rows]
