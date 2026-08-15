"""Ambiente de migrações do Alembic.

O URL da base de dados vem do ambiente, nunca do ficheiro de configuração: nenhum
segredo entra no repositório.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from braunprices.infrastructure.persistence.tables import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _database_url() -> str:
    url = os.environ.get("BRAUNPRICES_DATABASE_URL")
    if not url:
        message = (
            "BRAUNPRICES_DATABASE_URL não está definida. Copia o .env.example para "
            ".env e ajusta, ou exporta a variável antes de correr as migrações."
        )
        raise RuntimeError(message)
    return url


def run_migrations_offline() -> None:
    """Gera o SQL das migrações sem ligar à base de dados."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrações contra a base de dados."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
