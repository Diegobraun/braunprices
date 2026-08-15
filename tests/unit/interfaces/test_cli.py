from typer.testing import CliRunner

import braunprices
from braunprices.interfaces.cli.main import app

runner = CliRunner()


def test_version_prints_the_installed_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == braunprices.__version__


def test_it_stays_a_command_group_while_it_only_has_one_command() -> None:
    # Sem o callback, o typer colapsaria a aplicação no único comando registado e a
    # invocação mudaria de forma no dia em que o segundo comando entrasse.
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "version" in result.stdout


def test_invoking_without_arguments_shows_the_help() -> None:
    result = runner.invoke(app, [])
    assert "Usage" in result.stdout
