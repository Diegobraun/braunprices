"""Identificador estável de uma loja.

É estável no sentido forte: aparece em URLs públicos da API, em chaves de base de
dados e em ficheiros de configuração. Mudá-lo é uma migração, não uma renomeação.
"""

import re
from dataclasses import dataclass
from typing import Final

from braunprices.domain.errors import InvalidStoreSlugError

_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_MIN_LENGTH: Final[int] = 2
_MAX_LENGTH: Final[int] = 50


@dataclass(frozen=True, slots=True)
class StoreSlug:
    """Identificador em minúsculas, dígitos e hífens, sem hífen nas pontas."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):  # pragma: no cover - guarda de tipo
            raise InvalidStoreSlugError(f"Slug tem de ser texto, não {type(self.value).__name__}.")

        candidate = self.value.strip()
        if not (_MIN_LENGTH <= len(candidate) <= _MAX_LENGTH):
            raise InvalidStoreSlugError(
                f"{self.value!r} tem {len(candidate)} caracteres; o permitido é entre "
                f"{_MIN_LENGTH} e {_MAX_LENGTH}."
            )
        if not _PATTERN.fullmatch(candidate):
            raise InvalidStoreSlugError(
                f"{self.value!r} não é um slug válido: só minúsculas, dígitos e hífens, "
                f"sem hífen no início nem no fim."
            )
        object.__setattr__(self, "value", candidate)

    def __str__(self) -> str:
        return self.value
