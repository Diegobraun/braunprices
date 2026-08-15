"""Esquema inicial: lojas, produtos, referências de loja e observações de preço.

O histórico append-only não é apenas uma convenção do código: esta migração instala um
trigger que recusa UPDATE e DELETE em `price_observations`. Uma invariante que existe
só na camada de aplicação sobrevive até à primeira sessão de psql.

Revision ID: 0001
Revises:
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION braunprices_reject_history_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'price_observations e append-only: % nao e permitido. Uma observacao errada '
        'corrige-se registando outro facto, nunca sobrescrevendo o original.',
        TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

APPEND_ONLY_TRIGGER = """
CREATE TRIGGER price_observations_are_append_only
BEFORE UPDATE OR DELETE ON price_observations
FOR EACH ROW EXECUTE FUNCTION braunprices_reject_history_mutation();
"""


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_domain", sa.String(length=255), nullable=False),
        sa.Column("requests_per_second", sa.Float(), nullable=False),
        sa.Column("max_concurrency", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("backoff_base_seconds", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "requests_per_second > 0 AND requests_per_second <= 5",
            name="ck_stores_requests_per_second_is_conservative",
        ),
        sa.CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 4",
            name="ck_stores_max_concurrency_is_conservative",
        ),
        sa.PrimaryKeyConstraint("slug", name="pk_stores"),
        sa.UniqueConstraint("base_domain", name="uq_stores_base_domain"),
    )

    op.create_table(
        "products",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("ean", sa.String(length=13), nullable=True),
        sa.PrimaryKeyConstraint("product_id", name="pk_products"),
        sa.UniqueConstraint("ean", name="uq_products_ean"),
    )

    op.create_table(
        "store_listings",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_slug", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.product_id"],
            name="fk_store_listings_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["store_slug"],
            ["stores.slug"],
            name="fk_store_listings_store_slug_stores",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("listing_id", name="pk_store_listings"),
        sa.UniqueConstraint(
            "store_slug", "external_id", name="uq_store_listings_store_slug_external_id"
        ),
    )

    op.create_table(
        "price_observations",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_slug", sa.String(length=50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_day", sa.Date(), nullable=False),
        sa.Column("price_amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("price_currency", sa.String(length=3), nullable=False),
        sa.Column("availability", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("price_amount >= 0", name="ck_price_observations_price_is_not_negative"),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["store_listings.listing_id"],
            name="fk_price_observations_listing_id_store_listings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["store_slug"],
            ["stores.slug"],
            name="fk_price_observations_store_slug_stores",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("observation_id", name="pk_price_observations"),
        sa.UniqueConstraint(
            "listing_id",
            "observed_day",
            "price_amount",
            "price_currency",
            "availability",
            name="uq_price_observations_daily_fact",
        ),
    )

    op.create_index(
        "ix_price_observations_listing_id_observed_at",
        "price_observations",
        ["listing_id", sa.text("observed_at DESC")],
    )

    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS price_observations_are_append_only ON price_observations")
    op.execute("DROP FUNCTION IF EXISTS braunprices_reject_history_mutation()")
    op.drop_index("ix_price_observations_listing_id_observed_at", table_name="price_observations")
    op.drop_table("price_observations")
    op.drop_table("store_listings")
    op.drop_table("products")
    op.drop_table("stores")
