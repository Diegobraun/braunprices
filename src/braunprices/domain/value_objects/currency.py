"""Moeda ISO 4217, com o número de casas decimais que a define."""

from dataclasses import dataclass
from typing import Final

from braunprices.domain.errors import UnknownCurrencyError

# Número de casas decimais da unidade menor, por ISO 4217. A tabela é deliberadamente
# curta: cresce quando uma loja de outra moeda entrar, e não por antecipação.
_MINOR_UNITS: Final[dict[str, int]] = {
    "EUR": 2,
    "USD": 2,
    "GBP": 2,
    "CHF": 2,
    "BRL": 2,
    "PLN": 2,
    "SEK": 2,
    "DKK": 2,
    "NOK": 2,
    "JPY": 0,
}


@dataclass(frozen=True, slots=True)
class Currency:
    """Moeda identificada pelo código ISO 4217 alfabético.

    Construir diretamente é possível mas não recomendado: usa :meth:`of`, que valida
    o código contra a tabela de moedas conhecidas.
    """

    code: str
    minor_units: int

    @classmethod
    def of(cls, code: str) -> "Currency":
        """Devolve a moeda com este código ISO 4217.

        Levanta :class:`UnknownCurrencyError` se o código não constar da tabela — um código
        desconhecido significa que não sabemos quantas casas decimais a moeda tem, e
        adivinhar duas seria inventar uma regra de arredondamento.
        """
        normalized = code.strip().upper()
        try:
            return cls(code=normalized, minor_units=_MINOR_UNITS[normalized])
        except KeyError as exc:
            raise UnknownCurrencyError(
                f"Moeda desconhecida: {code!r}. Conhecidas: {sorted(_MINOR_UNITS)}."
            ) from exc

    def __str__(self) -> str:
        return self.code


EUR: Final[Currency] = Currency.of("EUR")
