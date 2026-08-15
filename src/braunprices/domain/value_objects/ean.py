"""Código de barras de produto, com o dígito de controlo validado.

Um EAN inválido não é representável neste sistema: a construção falha. Isto importa
porque o EAN é a chave de casamento entre lojas — um dígito trocado não produz um
produto errado, produz um casamento errado entre duas lojas, que é mais difícil de
detetar depois.
"""

from dataclasses import dataclass
from typing import Final

from braunprices.domain.errors import InvalidEANError

# Comprimentos aceites. O GTIN-14 fica de fora de propósito: identifica unidades
# logísticas (caixas, paletes), não o artigo que um consumidor compra numa loja online.
_UPC_A_LENGTH: Final[int] = 12
_ACCEPTED_LENGTHS: Final[frozenset[int]] = frozenset({8, _UPC_A_LENGTH, 13})


@dataclass(frozen=True, slots=True)
class EAN:
    """EAN-8 ou EAN-13 válido.

    Um UPC-A de 12 dígitos é aceite e normalizado para EAN-13 com um zero à cabeça,
    que é a forma como o GS1 define a equivalência. Sem essa normalização, a mesma
    referência viria de duas lojas com dois valores diferentes e nunca casaria.
    """

    value: str

    def __post_init__(self) -> None:
        digits = _extract_digits(self.value)

        if len(digits) not in _ACCEPTED_LENGTHS:
            raise InvalidEANError(
                f"{self.value!r} tem {len(digits)} dígitos; são aceites "
                f"{sorted(_ACCEPTED_LENGTHS)}."
            )
        if not _has_valid_check_digit(digits):
            raise InvalidEANError(f"Dígito de controlo inválido em {self.value!r}.")

        normalized = digits.zfill(13) if len(digits) == _UPC_A_LENGTH else digits
        object.__setattr__(self, "value", normalized)

    @property
    def length(self) -> int:
        """Número de dígitos após normalização: 8 ou 13."""
        return len(self.value)

    def __str__(self) -> str:
        return self.value


def _extract_digits(raw: str) -> str:
    """Aceita separadores e espaços à volta, recusa qualquer outro caractere."""
    if not isinstance(raw, str):  # pragma: no cover - guarda de tipo
        raise InvalidEANError(f"EAN tem de ser texto, não {type(raw).__name__}.")
    candidate = raw.strip().replace(" ", "").replace("-", "")
    if not candidate:
        raise InvalidEANError("EAN vazio.")
    if not candidate.isdigit():
        raise InvalidEANError(f"{raw!r} contém caracteres que não são dígitos.")
    return candidate


def _has_valid_check_digit(digits: str) -> bool:
    """Aplica o módulo 10 do GS1, igual para EAN-8, UPC-A e EAN-13.

    Os pesos alternam 3 e 1 a partir do dígito imediatamente à esquerda do dígito de
    controlo, o que torna o cálculo independente do comprimento.
    """
    body, check_digit = digits[:-1], int(digits[-1])
    total = sum(
        int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body))
    )
    return (10 - total % 10) % 10 == check_digit
