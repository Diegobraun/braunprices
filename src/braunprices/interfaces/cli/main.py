"""Ponto de entrada da CLI de operação do BraunPrices."""

import typer

from braunprices import __version__

app = typer.Typer(
    name="braunprices",
    help="Operação do rastreador de histórico de preços do retalho português.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Agrupa os subcomandos.

    Existe para que ``braunprices`` continue a ser um grupo de comandos mesmo enquanto
    só houver um: sem isto, o typer colapsa a aplicação no único comando registado e a
    invocação muda de forma assim que o segundo comando entrar.
    """


@app.command()
def version() -> None:
    """Mostra a versão instalada."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
