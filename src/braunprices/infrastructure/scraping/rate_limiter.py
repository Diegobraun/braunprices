"""Rate limit por domínio, com recuo exponencial.

O ritmo é por domínio e não global: duas lojas diferentes não têm nada que ver uma com
a outra, e somar os pedidos das duas num só contador tornaria a recolha mais lenta sem
proteger ninguém.

O relógio é injetável para que os testes não tenham de esperar de verdade. Um teste de
rate limit que dorme três segundos é um teste que ninguém corre.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class DomainRateLimiter:
    """Espaça os pedidos a cada domínio pelo intervalo mínimo configurado."""

    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _next_allowed_at: dict[str, float] = field(default_factory=dict, repr=False)

    def wait_for_turn(self, domain: str, min_interval_seconds: float) -> float:
        """Espera o necessário até poder pedir a este domínio, e devolve quanto esperou."""
        now = self.monotonic()
        allowed_at = self._next_allowed_at.get(domain, now)
        delay = max(0.0, allowed_at - now)
        if delay > 0:
            self.sleep(delay)
        self._next_allowed_at[domain] = max(now, allowed_at) + min_interval_seconds
        return delay

    def back_off(self, domain: str, seconds: float) -> None:
        """Empurra a próxima janela deste domínio para daqui a ``seconds``.

        Usado depois de uma resposta que peça calma. O recuo aplica-se ao domínio
        inteiro e não ao URL: quem está a travar está a travar o cliente, não a página.
        """
        self._next_allowed_at[domain] = self.monotonic() + seconds


def exponential_backoff_seconds(attempt: int, base_seconds: float) -> float:
    """Segundos a esperar antes da tentativa ``attempt``, contada a partir de 1.

    Sem aleatoriedade: com um único cliente a falar com um único domínio de cada vez,
    não há bando de clientes a sincronizar-se, e a previsibilidade vale mais nos
    registos do que a dispersão valeria na rede.
    """
    if attempt < 1:
        message = f"attempt começa em 1, não em {attempt}."
        raise ValueError(message)
    return base_seconds**attempt if base_seconds > 1 else base_seconds * attempt
