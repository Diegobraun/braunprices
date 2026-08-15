"""Teste trivial da Fase 0: o pacote instala e é importável."""

import pytest

import braunprices


@pytest.mark.unit
def test_package_exposes_version() -> None:
    assert braunprices.__version__.count(".") == 2
