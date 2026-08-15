"""Esquema relacional, em SQLAlchemy Core.

Tabelas, não modelos ORM. As entidades do domínio são ``dataclass`` congeladas com
``slots``, e o mapeamento imperativo do ORM precisa de instrumentar e escrever
atributos ao carregar — o que obrigaria a abrir mão de ``frozen`` em
``PriceObservation``, a invariante de que depende tudo o resto. A tradução entre
linha e entidade é explícita e vive em ``mappers.py``. Ver ADR-0009.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql

# Convenção de nomes explícita: sem ela, o Alembic gera nomes automáticos que mudam
# entre versões e tornam as migrações irrepetíveis.
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

stores = Table(
    "stores",
    metadata,
    Column("slug", String(50), primary_key=True),
    Column("name", Text, nullable=False),
    Column("base_domain", String(255), nullable=False, unique=True),
    Column("requests_per_second", Float, nullable=False),
    Column("max_concurrency", Integer, nullable=False),
    Column("timeout_seconds", Float, nullable=False),
    Column("max_retries", Integer, nullable=False),
    Column("backoff_base_seconds", Float, nullable=False),
    CheckConstraint(
        "requests_per_second > 0 AND requests_per_second <= 5",
        name="requests_per_second_is_conservative",
    ),
    CheckConstraint(
        "max_concurrency >= 1 AND max_concurrency <= 4",
        name="max_concurrency_is_conservative",
    ),
)

products = Table(
    "products",
    metadata,
    Column("product_id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column("canonical_name", Text, nullable=False),
    # Nulo é permitido e frequente: um produto sem EAN existe, apenas não participa
    # do casamento entre lojas. Único quando presente, porque o EAN é a chave desse
    # casamento e dois produtos com o mesmo EAN seriam o mesmo produto.
    Column("ean", String(13), nullable=True, unique=True),
)

store_listings = Table(
    "store_listings",
    metadata,
    Column("listing_id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column(
        "product_id",
        postgresql.UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "store_slug",
        String(50),
        ForeignKey("stores.slug", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("external_id", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    UniqueConstraint("store_slug", "external_id", name="uq_store_listings_store_slug_external_id"),
)

price_observations = Table(
    "price_observations",
    metadata,
    Column("observation_id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column(
        "listing_id",
        postgresql.UUID(as_uuid=True),
        ForeignKey("store_listings.listing_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "store_slug", String(50), ForeignKey("stores.slug", ondelete="RESTRICT"), nullable=False
    ),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    # O dia de Lisboa a que a observação pertence. Guardado, não calculado: em
    # PostgreSQL, `AT TIME ZONE 'Europe/Lisbon'` é STABLE e não IMMUTABLE, logo não
    # pode ser coluna gerada nem entrar num índice. O domínio é a autoridade sobre
    # que dia é este, e um teste de integração garante que os dois concordam.
    Column("observed_day", Date, nullable=False),
    Column("price_amount", Numeric(14, 4), nullable=False),
    Column("price_currency", String(3), nullable=False),
    Column("availability", String(32), nullable=False),
    Column("source_url", Text, nullable=False),
    Column("raw_hash", Text, nullable=False),
    CheckConstraint("price_amount >= 0", name="price_is_not_negative"),
    # Idempotência da passagem diária: duas execuções no mesmo dia que vejam o mesmo
    # preço e a mesma disponibilidade descrevem o mesmo facto, e o segundo INSERT é
    # ignorado. Se o preço mudou durante o dia, a chave difere e o facto novo entra —
    # que é precisamente o que se quer registar.
    UniqueConstraint(
        "listing_id",
        "observed_day",
        "price_amount",
        "price_currency",
        "availability",
        name="uq_price_observations_daily_fact",
    ),
)

# A consulta dominante é "o histórico desta referência, do mais recente para trás".
# Declarado fora da tabela para poder ordenar a coluna por descendente, que é a
# ordem em que é lida.
Index(
    "ix_price_observations_listing_id_observed_at",
    price_observations.c.listing_id,
    price_observations.c.observed_at.desc(),
)


# --------------------------------------------------------------------------
# Observabilidade da recolha
#
# Os relatos são guardados, e não apenas registados num log. Uma degradação silenciosa
# reconhece-se ao comparar hoje com a semana passada, e para isso a semana passada tem
# de continuar a existir em sítio consultável.
# --------------------------------------------------------------------------

collection_runs = Table(
    "collection_runs",
    metadata,
    Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column(
        "store_slug", String(50), ForeignKey("stores.slug", ondelete="RESTRICT"), nullable=False
    ),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("listings_planned", Integer, nullable=False),
    Column("pages_fetched", Integer, nullable=False),
    Column("observations_recorded", Integer, nullable=False),
    Column("prices_changed", Integer, nullable=False),
    Column("observations_from_json_ld", Integer, nullable=False),
    Column("observations_from_html_fallback", Integer, nullable=False),
    Column("stopped_early_because", Text, nullable=True),
)

collection_failures = Table(
    "collection_failures",
    metadata,
    Column("failure_id", postgresql.UUID(as_uuid=True), primary_key=True),
    Column(
        "run_id",
        postgresql.UUID(as_uuid=True),
        ForeignKey("collection_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
    Column("url", Text, nullable=False),
    Column("reason", String(40), nullable=False),
    Column("detail", Text, nullable=False),
    Column("http_status", Integer, nullable=True),
)

# A pergunta que o painel faz primeiro é "como correu a última passagem desta loja".
Index(
    "ix_collection_runs_store_slug_started_at",
    collection_runs.c.store_slug,
    collection_runs.c.started_at.desc(),
)

# E a seguir: "que falhas houve nesta passagem, agrupadas por padrão".
Index(
    "ix_collection_failures_run_id_reason",
    collection_failures.c.run_id,
    collection_failures.c.reason,
)
