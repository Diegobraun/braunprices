"""A regra de dependência da arquitetura limpa é verificada, não confiada.

Os contratos vivem em ``pyproject.toml``, secção ``[tool.importlinter]``. Este teste
corre exatamente o mesmo executável que a CI corre, para que ``make test`` sozinho já
apanhe uma violação sem depender de o programador se lembrar de correr ``lint-imports``.

Correr o executável (em vez de ``python -m importlinter.cli``, que devolve 0 sempre por
o grupo de comandos nunca chegar a ser invocado) é deliberado: um guarda que não falha
quando a regra é quebrada é dívida disfarçada de cobertura.
"""

import subprocess
import sys
from pathlib import Path

import pytest

LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"


@pytest.mark.architecture
def test_lint_imports_executable_is_available() -> None:
    assert LINT_IMPORTS.is_file(), (
        f"{LINT_IMPORTS} não existe — o ambiente não foi criado com `make setup`."
    )


@pytest.mark.architecture
def test_import_contracts_hold() -> None:
    result = subprocess.run(  # noqa: S603 - argv fixo, derivado de sys.executable
        [str(LINT_IMPORTS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr
