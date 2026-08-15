import pytest
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


def test_the_serve_command_binds_locally_unless_told_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Expor uma porta à rede é uma decisão de operação, tomada por escrito num ficheiro
    # de serviço — não por omissão de um comando.
    captured: dict[str, object] = {}

    def fake_run(app_path: str, **options: object) -> None:
        captured["app"] = app_path
        captured.update(options)

    monkeypatch.setattr("uvicorn.run", fake_run)
    result = runner.invoke(app, ["servir"])

    assert result.exit_code == 0, result.stdout
    assert captured["app"] == "braunprices.interfaces.api.app:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert captured["reload"] is False
