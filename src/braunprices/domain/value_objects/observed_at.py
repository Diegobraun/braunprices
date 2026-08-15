"""Carimbo temporal de uma observação de preço.

A lei fala em dias, e "dia" só tem significado dentro de um fuso. O fuso deste
domínio é ``Europe/Lisbon``: é onde as lojas praticam os preços e é o calendário
contra o qual uma fiscalização contaria os 30 dias.

O instante é guardado em UTC e convertido para o fuso local apenas quando se pergunta
a que dia pertence. Guardar diretamente em hora local perderia a distinção entre as
duas ocorrências de 01:30 na noite em que o relógio recua.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Final
from zoneinfo import ZoneInfo

from braunprices.domain.errors import InvalidObservedAtError

LISBON: Final[ZoneInfo] = ZoneInfo("Europe/Lisbon")


@dataclass(frozen=True, slots=True)
class ObservedAt:
    """Instante em que um preço foi lido, sempre com fuso conhecido.

    Um ``datetime`` sem fuso é recusado: seria uma hora sem sítio, e a fronteira de
    dia deixaria de ser determinável.
    """

    instant: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.instant, datetime):  # pragma: no cover - guarda de tipo
            raise InvalidObservedAtError(
                f"Instante tem de ser datetime, não {type(self.instant).__name__}."
            )
        if self.instant.tzinfo is None or self.instant.utcoffset() is None:
            raise InvalidObservedAtError(
                f"{self.instant!r} não tem fuso horário. Um instante sem fuso não "
                f"determina a que dia pertence."
            )
        object.__setattr__(self, "instant", self.instant.astimezone(UTC))

    @classmethod
    def from_lisbon(cls, moment: datetime) -> "ObservedAt":
        """Interpreta um ``datetime`` sem fuso como hora de Lisboa.

        Serve os testes e a leitura de dados legados. Código de produção deve receber
        o instante já com fuso, vindo de quem o observou.
        """
        if moment.tzinfo is not None:
            raise InvalidObservedAtError(
                "from_lisbon recebe um datetime sem fuso; este já traz um. Constrói "
                "ObservedAt diretamente."
            )
        return cls(instant=moment.replace(tzinfo=LISBON))

    @property
    def local_date(self) -> date:
        """Dia a que a observação pertence no calendário de Lisboa."""
        return self.instant.astimezone(LISBON).date()

    @property
    def local_datetime(self) -> datetime:
        """O mesmo instante, expresso na hora de Lisboa."""
        return self.instant.astimezone(LISBON)

    def __lt__(self, other: "ObservedAt") -> bool:
        return self.instant < other.instant

    def __le__(self, other: "ObservedAt") -> bool:
        return self.instant <= other.instant

    def __gt__(self, other: "ObservedAt") -> bool:
        return self.instant > other.instant

    def __ge__(self, other: "ObservedAt") -> bool:
        return self.instant >= other.instant

    def __str__(self) -> str:
        return self.instant.isoformat()
