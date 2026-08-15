"""A janela de dias sobre a qual a regra legal é calculada.

A redação fala nos "30 dias consecutivos **anteriores** à aplicação do desconto".
"Anteriores" exclui o próprio dia da aplicação: a janela vai de ``reference_date - 30``
(inclusive) até ``reference_date`` (exclusive).

Incluir o dia da aplicação deixaria entrar no cálculo o preço já promocional desse dia
— precisamente o número que a lei quer manter de fora — porque não sabemos a que hora
a loja aplicou o desconto.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from braunprices.domain.errors import InvalidPriceWindowError

DEFAULT_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class PriceWindow:
    """Intervalo de dias de Lisboa, fechado à esquerda e aberto à direita."""

    reference_date: date
    window_days: int = DEFAULT_WINDOW_DAYS

    def __post_init__(self) -> None:
        # Exige `date` exato, e não uma subclasse. `datetime` é subclasse de `date` e
        # passaria despercebido, trazendo consigo uma hora que a janela não usa — e
        # com ela a ilusão de que a fronteira é ao instante e não ao dia.
        if type(self.reference_date) is not date:
            raise InvalidPriceWindowError(
                f"reference_date tem de ser date, não {type(self.reference_date).__name__}. "
                f"A janela conta dias de Lisboa, não instantes."
            )
        if self.window_days < 1:
            raise InvalidPriceWindowError(
                f"window_days={self.window_days} não é uma janela. O mínimo é 1 dia."
            )

    @property
    def start(self) -> date:
        """Primeiro dia incluído na janela."""
        return self.reference_date - timedelta(days=self.window_days)

    @property
    def end_exclusive(self) -> date:
        """Primeiro dia já fora da janela — o dia da aplicação do desconto."""
        return self.reference_date

    def contains(self, day: date) -> bool:
        """Indica se este dia de Lisboa cai dentro da janela."""
        return self.start <= day < self.end_exclusive

    def __str__(self) -> str:
        return f"[{self.start.isoformat()}, {self.end_exclusive.isoformat()})"
