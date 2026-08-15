"""CLI de operação do BraunPrices.

É por aqui que a recolha diária é disparada. O agendamento vive fora do processo — cron
ou um temporizador do systemd — e não num agendador interno: um processo que corre uma
vez por dia e sai é mais fácil de supervisionar, de repetir à mão e de perceber quando
falha do que um daemon que tem de estar de pé para o dia acontecer. Ver `docs/operacao.md`.
"""

import sys
from typing import Annotated
from uuid import uuid4

import typer

from braunprices import __version__
from braunprices.application.use_cases.collect_store_prices import StoreNotConfiguredError
from braunprices.domain.model.collection_run import CollectionReport
from braunprices.domain.model.product import Product, StoreListing
from braunprices.domain.model.store import RateLimitPolicy, Store
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.composition import build_container
from braunprices.infrastructure.config import get_settings
from braunprices.infrastructure.logging import configure_logging

app = typer.Typer(
    name="braunprices",
    help="Operação do rastreador de histórico de preços do retalho português.",
    no_args_is_help=True,
)
stores_app = typer.Typer(help="Gestão das lojas de que se recolhe.")
listings_app = typer.Typer(help="Gestão das referências de produto a visitar.")
app.add_typer(stores_app, name="lojas")
app.add_typer(listings_app, name="referencias")


@app.callback()
def main() -> None:
    """Agrupa os subcomandos e prepara o registo estruturado."""
    settings = get_settings()
    configure_logging(level=settings.log_level, output_format=settings.log_format)


@app.command()
def version() -> None:
    """Mostra a versão instalada."""
    typer.echo(__version__)


@app.command()
def recolher(
    loja: Annotated[str, typer.Argument(help="Slug da loja, por exemplo `worten`.")],
    limite: Annotated[
        int | None,
        typer.Option(help="Recolhe no máximo estas referências. Útil para a primeira vez."),
    ] = None,
) -> None:
    """Corre uma passagem de recolha a uma loja.

    É idempotente: correr duas vezes no mesmo dia com o mesmo resultado não duplica
    nada. Se o preço mudou entre passagens, a segunda regista o facto novo.
    """
    settings = get_settings()
    container = build_container(settings)
    slug = StoreSlug(loja)

    with container.unit_of_work() as work:
        store = work.stores.get(slug)
    if store is None:
        typer.secho(
            f"A loja {loja!r} não está registada. Regista-a com `braunprices lojas registar`.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        report = container.collect_prices_for(store)(slug, limit=limite)
    except StoreNotConfiguredError as error:  # pragma: no cover - já apanhado acima
        typer.secho(str(error), fg=typer.colors.RED)
        raise typer.Exit(code=1) from error

    _print_report(report)
    # Sai com código diferente de zero quando a passagem merece que alguém lhe pegue,
    # para que o agendador ou a supervisão dêem por isso sem ninguém ler o output.
    if report.is_worth_investigating:
        raise typer.Exit(code=2)


@app.command()
def estado(
    loja: Annotated[str, typer.Argument(help="Slug da loja.")],
    passagens: Annotated[int, typer.Option(help="Quantas passagens mostrar.")] = 5,
) -> None:
    """Mostra como correram as últimas passagens a uma loja."""
    container = build_container(get_settings())
    slug = StoreSlug(loja)
    with container.unit_of_work() as work:
        recent = work.reports.recent_for_store(slug, limit=passagens)

    if not recent:
        typer.echo(f"Ainda não há passagens registadas para {loja}.")
        return
    for report in recent:
        _print_report(report)
        typer.echo("")


@stores_app.command("registar")
def register_store(
    slug: Annotated[str, typer.Argument(help="Identificador estável, por exemplo `worten`.")],
    nome: Annotated[str, typer.Option(help="Nome da loja.")],
    dominio: Annotated[str, typer.Option(help="Domínio base, sem esquema nem caminho.")],
    pedidos_por_segundo: Annotated[float, typer.Option(help="Ritmo máximo.")] = 0.5,
) -> None:
    """Regista uma loja e a política de ritmo com que será visitada."""
    container = build_container(get_settings())
    store = Store(
        slug=StoreSlug(slug),
        name=nome,
        base_domain=dominio,
        rate_limit=RateLimitPolicy(requests_per_second=pedidos_por_segundo),
    )
    with container.unit_of_work() as work:
        if work.stores.get(store.slug) is not None:
            typer.secho(f"A loja {slug!r} já está registada.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=1)
        work.stores.add(store)
        work.commit()
    typer.secho(
        f"Loja {slug!r} registada a {store.rate_limit.requests_per_second} pedidos/s "
        f"({store.rate_limit.min_interval_seconds:.1f} s entre pedidos).",
        fg=typer.colors.GREEN,
    )


@stores_app.command("listar")
def list_stores() -> None:
    """Lista as lojas registadas."""
    container = build_container(get_settings())
    with container.unit_of_work() as work:
        stores = work.stores.list_all()
    if not stores:
        typer.echo("Sem lojas registadas.")
        return
    for store in stores:
        typer.echo(
            f"{store.slug}  {store.name}  {store.base_domain}  "
            f"{store.rate_limit.requests_per_second} pedidos/s"
        )


@listings_app.command("adicionar")
def add_listing(
    loja: Annotated[str, typer.Argument(help="Slug da loja.")],
    url: Annotated[str, typer.Argument(help="URL absoluto da página de produto.")],
    referencia: Annotated[str, typer.Option(help="Identificador do produto na loja (SKU).")],
    nome: Annotated[str, typer.Option(help="Nome do produto.")],
    ean: Annotated[str | None, typer.Option(help="Código de barras, se conhecido.")] = None,
) -> None:
    """Acrescenta uma referência de produto para passar a ser visitada.

    Se o EAN já existir noutro produto, a referência é ligada a esse produto — que é
    como o casamento entre lojas acontece.
    """
    container = build_container(get_settings())
    slug = StoreSlug(loja)
    barcode = EAN(ean) if ean else None

    with container.unit_of_work() as work:
        if work.stores.get(slug) is None:
            typer.secho(f"A loja {loja!r} não está registada.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        listing = StoreListing(listing_id=uuid4(), store_slug=slug, external_id=referencia, url=url)
        existing = work.products.get_by_ean(barcode) if barcode else None
        if existing is not None:
            existing.add_listing(listing)
            work.products.save(existing)
            typer.secho(
                f"Referência ligada ao produto que já existia com o EAN {barcode}.",
                fg=typer.colors.GREEN,
            )
        else:
            work.products.add(
                Product(
                    product_id=uuid4(),
                    canonical_name=nome,
                    ean=barcode,
                    listings=[listing],
                )
            )
            typer.secho(
                f"Produto e referência criados ({listing.listing_id}).", fg=typer.colors.GREEN
            )
        work.commit()


def _print_report(report: CollectionReport) -> None:
    """Escreve o relato de uma passagem em texto legível."""
    duration = ""
    if report.finished_at is not None:
        seconds = (report.finished_at.instant - report.started_at.instant).total_seconds()
        duration = f" em {seconds:.0f}s"

    typer.echo(f"[{report.store_slug}] {report.started_at.local_datetime:%Y-%m-%d %H:%M}{duration}")
    typer.echo(
        f"  {report.pages_fetched}/{report.listings_planned} páginas · "
        f"{report.observations_recorded} observações novas · "
        f"{report.prices_changed} preços alterados"
    )
    typer.echo(f"  sucesso {report.success_rate:.1%} · recurso ao HTML {report.fallback_rate:.1%}")
    for reason, count in sorted(report.failures_by_reason.items(), key=lambda item: -item[1]):
        typer.echo(f"  falha {reason.value}: {count}")
    if report.stopped_early_because:
        typer.secho(f"  parou cedo: {report.stopped_early_because}", fg=typer.colors.YELLOW)
    if report.is_worth_investigating:
        typer.secho("  esta passagem merece ser investigada.", fg=typer.colors.YELLOW)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
