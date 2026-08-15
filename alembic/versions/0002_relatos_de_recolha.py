"""Relatos de recolha: quantas páginas, quantas falhas, quantos preços mudaram.

Guardar os relatos, e não apenas registá-los num log, é o que permite reconhecer uma
degradação silenciosa: a comparação é entre hoje e a semana passada, e para isso a
semana passada tem de continuar a existir em sítio consultável.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_slug", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listings_planned", sa.Integer(), nullable=False),
        sa.Column("pages_fetched", sa.Integer(), nullable=False),
        sa.Column("observations_recorded", sa.Integer(), nullable=False),
        sa.Column("prices_changed", sa.Integer(), nullable=False),
        sa.Column("observations_from_json_ld", sa.Integer(), nullable=False),
        sa.Column("observations_from_html_fallback", sa.Integer(), nullable=False),
        sa.Column("stopped_early_because", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["store_slug"],
            ["stores.slug"],
            name="fk_collection_runs_store_slug_stores",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_collection_runs"),
    )

    op.create_table(
        "collection_failures",
        sa.Column("failure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        # CASCADE aqui, ao contrário do resto do esquema: uma falha não é um facto
        # sobre a loja, é um detalhe do relato a que pertence, e não faz sentido
        # sobreviver-lhe.
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["collection_runs.run_id"],
            name="fk_collection_failures_run_id_collection_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("failure_id", name="pk_collection_failures"),
    )

    op.create_index(
        "ix_collection_runs_store_slug_started_at",
        "collection_runs",
        ["store_slug", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_collection_failures_run_id_reason",
        "collection_failures",
        ["run_id", "reason"],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_failures_run_id_reason", table_name="collection_failures")
    op.drop_index("ix_collection_runs_store_slug_started_at", table_name="collection_runs")
    op.drop_table("collection_failures")
    op.drop_table("collection_runs")
