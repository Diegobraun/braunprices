"""Configuração comum à suite.

Os markers são aplicados pela pasta em que o teste vive, em vez de decorados um a um.
Um marker esquecido faria o teste escapar a ``pytest -m unit``, e um teste que não corre
é pior do que um teste que não existe: dá a impressão de cobertura sem a dar.
"""

from pathlib import Path

import pytest

_MARKER_BY_DIRECTORY = {
    "unit": "unit",
    "integration": "integration",
    "architecture": "architecture",
}

TESTS_ROOT = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marca cada teste conforme a pasta de topo em que está."""
    for item in items:
        relative = Path(str(item.fspath)).relative_to(TESTS_ROOT)
        marker = _MARKER_BY_DIRECTORY.get(relative.parts[0])
        if marker is not None:
            item.add_marker(getattr(pytest.mark, marker))
