"""A regra de dependência da arquitetura limpa é verificada, não confiada.

Os contratos vivem em ``pyproject.toml``, secção ``[tool.importlinter]``. Este teste
corre exatamente o mesmo executável que a CI corre, para que ``make test`` sozinho já
apanhe uma violação sem depender de o programador se lembrar de correr ``lint-imports``.

Correr o executável (em vez de ``python -m importlinter.cli``, que devolve 0 sempre por
o grupo de comandos nunca chegar a ser invocado) é deliberado: um guarda que não falha
quando a regra é quebrada é dívida disfarçada de cobertura.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"


def _environment_with_src_on_the_path() -> dict[str, str]:
    """Garante que o subprocess encontra o pacote sem depender do editable install.

    O pytest já põe ``src`` no caminho por configuração, mas um subprocess não herda
    isso. Em macOS, um ``.pth`` com a flag ``UF_HIDDEN`` é ignorado sem aviso e o
    editable install fica inerte — e o guarda de arquitetura passaria a falhar por
    uma razão que nada tem a ver com a arquitetura.
    """
    environment = dict(os.environ)
    source_root = str(PROJECT_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{source_root}{os.pathsep}{existing}" if existing else source_root
    return environment


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
        cwd=PROJECT_ROOT,
        env=_environment_with_src_on_the_path(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
