"""As migrações são o que corre em produção, logo são o que se testa.

Criar o esquema com ``metadata.create_all`` nos testes deixaria por cobrir exatamente
o ficheiro mais fácil de escrever errado, e a divergência só apareceria no dia da
primeira migração real.
"""

from sqlalchemy import Connection, Engine, inspect, text

from braunprices.infrastructure.persistence.tables import metadata


def test_every_table_the_code_expects_exists(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    declared = {table.name for table in metadata.sorted_tables}
    assert declared <= set(inspector.get_table_names())


def test_the_migration_and_the_table_definitions_agree_on_columns(
    migrated_engine: Engine,
) -> None:
    # A divergência entre o que o código declara e o que a migração criou é silenciosa
    # até uma consulta rebentar em produção.
    inspector = inspect(migrated_engine)
    for table in metadata.sorted_tables:
        migrated = {column["name"] for column in inspector.get_columns(table.name)}
        assert {column.name for column in table.columns} == migrated, table.name


def test_the_dominant_query_has_its_index(migrated_engine: Engine) -> None:
    # "O histórico desta referência, do mais recente para trás" é a consulta que a API
    # faz a toda a hora. Sem índice, cresce linearmente com o histórico acumulado —
    # que é precisamente o que se espera que cresça.
    indexes = inspect(migrated_engine).get_indexes("price_observations")
    assert "ix_price_observations_listing_id_observed_at" in {index["name"] for index in indexes}


def test_the_index_is_actually_used_for_the_dominant_query(connection: Connection) -> None:
    # Numa tabela vazia o planner faz sempre uma varredura sequencial, e o teste
    # passaria a dizer apenas que o índice existe — o que já está coberto acima. Só
    # com histórico acumulado é que a escolha do planner significa alguma coisa, e é
    # com histórico acumulado que este sistema vai viver.
    connection.execute(
        text(
            """
            INSERT INTO stores VALUES
                ('volume', 'Volume', 'volume.pt', 0.5, 1, 20, 3, 2);
            INSERT INTO products (product_id, canonical_name, ean)
                SELECT gen_random_uuid(), 'Produto ' || n, NULL
                FROM generate_series(1, 200) AS n;
            INSERT INTO store_listings (listing_id, product_id, store_slug, external_id, url)
                SELECT gen_random_uuid(), product_id, 'volume', product_id::text,
                       'https://volume.pt/p/' || product_id
                FROM products;
            INSERT INTO price_observations (
                observation_id, listing_id, store_slug, observed_at, observed_day,
                price_amount, price_currency, availability, source_url, raw_hash)
                SELECT gen_random_uuid(), l.listing_id, 'volume',
                       (DATE '2026-01-01' + d)::timestamptz,
                       DATE '2026-01-01' + d,
                       10 + d, 'EUR', 'in_stock', l.url, 'sha256:' || d
                FROM store_listings l, generate_series(0, 59) AS d
                WHERE l.store_slug = 'volume';
            ANALYZE price_observations;
            """
        )
    )
    a_listing_id = connection.execute(
        text("SELECT listing_id FROM store_listings WHERE store_slug = 'volume' LIMIT 1")
    ).scalar_one()

    plan = "\n".join(
        connection.execute(
            text(
                "EXPLAIN SELECT * FROM price_observations WHERE listing_id = :listing "
                "ORDER BY observed_at DESC LIMIT 20"
            ),
            {"listing": a_listing_id},
        ).scalars()
    )
    assert "ix_price_observations_listing_id_observed_at" in plan, plan
    assert "Seq Scan" not in plan, plan


def test_the_append_only_trigger_is_installed(connection: Connection) -> None:
    installed = connection.execute(
        text(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgrelid = 'price_observations'::regclass"
        )
    ).scalars()
    assert "price_observations_are_append_only" in set(installed)


def test_timestamps_keep_their_time_zone(connection: Connection) -> None:
    # Um TIMESTAMP sem fuso tornaria a fronteira de dia indeterminável assim que os
    # dados saíssem do processo que os escreveu. Perguntado ao próprio PostgreSQL, e
    # não ao que o SQLAlchemy julga ter pedido.
    declared = connection.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'price_observations' AND column_name = 'observed_at'"
        )
    ).scalar_one()
    assert declared == "timestamp with time zone"
