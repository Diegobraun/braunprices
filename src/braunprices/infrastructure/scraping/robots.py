"""Verificação do ``robots.txt``, em runtime e a cada URL.

Não basta ler o ficheiro uma vez durante a implementação e escrever o adaptador de
acordo: a loja pode mudar as regras a qualquer momento, e quem as respeita só no dia em
que as leu não as está a respeitar.

A política em caso de dúvida é **não pedir**. Se o ``robots.txt`` não puder ser obtido
ou não puder ser lido, o domínio fica interdito até haver resposta. Assumir permissão
por não se ter conseguido perguntar é a definição prática de não perguntar.
"""

import time
from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Quanto tempo uma decisão sobre um domínio se mantém válida. Uma passagem diária
# demora horas, e reler o robots.txt a cada página seria tráfego desnecessário sobre a
# própria loja; um dia é curto o suficiente para apanhar uma mudança de política antes
# da passagem seguinte.
DEFAULT_CACHE_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    """O que o ``robots.txt`` diz sobre um URL, e porquê."""

    is_allowed: bool
    reason: str
    crawl_delay_seconds: float | None = None


@dataclass
class RobotsPolicy:
    """Guarda e aplica as regras de ``robots.txt`` por domínio.

    O user-agent com que se pergunta é o mesmo com que se pede a página. Perguntar com
    um nome e pedir com outro tornaria a resposta irrelevante.
    """

    user_agent: str
    http_client: httpx.Client
    cache_seconds: int = DEFAULT_CACHE_SECONDS
    _parsers: dict[str, tuple[RobotFileParser | None, float]] = field(
        default_factory=dict, repr=False
    )

    def is_allowed(self, url: str) -> RobotsDecision:
        """Decide se este URL pode ser pedido."""
        origin = _origin_of(url)
        if origin is None:
            return RobotsDecision(is_allowed=False, reason=f"URL sem origem utilizável: {url!r}")

        parser = self._parser_for(origin)
        if parser is None:
            return RobotsDecision(
                is_allowed=False,
                reason=(
                    f"Não foi possível obter o robots.txt de {origin}. Sem resposta, o "
                    f"domínio fica interdito: presumir permissão seria não perguntar."
                ),
            )

        allowed = parser.can_fetch(self.user_agent, url)
        return RobotsDecision(
            is_allowed=allowed,
            reason=(
                f"Permitido pelo robots.txt de {origin}."
                if allowed
                else f"Proibido pelo robots.txt de {origin} para {self.user_agent!r}."
            ),
            crawl_delay_seconds=_crawl_delay(parser, self.user_agent),
        )

    def _parser_for(self, origin: str) -> RobotFileParser | None:
        cached = self._parsers.get(origin)
        if cached is not None and time.monotonic() - cached[1] < self.cache_seconds:
            return cached[0]

        parser = self._download(origin)
        self._parsers[origin] = (parser, time.monotonic())
        return parser

    def _download(self, origin: str) -> RobotFileParser | None:
        robots_url = f"{origin}/robots.txt"
        try:
            response = self.http_client.get(robots_url, follow_redirects=True)
        except httpx.HTTPError as error:
            logger.warning("robots.indisponivel", origin=origin, erro=str(error))
            return None

        # 404 sem robots.txt significa que a loja não publicou regras, e o padrão diz
        # que nesse caso tudo é permitido. É a única forma de ausência que se lê como
        # permissão, porque é a que o próprio protocolo define.
        if response.status_code == httpx.codes.NOT_FOUND:
            parser = RobotFileParser()
            parser.parse([])
            return parser

        if response.status_code >= httpx.codes.BAD_REQUEST:
            logger.warning("robots.recusado", origin=origin, status=response.status_code)
            return None

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


def _origin_of(url: str) -> str | None:
    parsed = httpx.URL(url)
    if not parsed.scheme or not parsed.host:
        return None
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.host}{port}"


def _crawl_delay(parser: RobotFileParser, user_agent: str) -> float | None:
    """Lê o ``Crawl-delay`` declarado, quando existe.

    Quando a loja declara um ritmo, é esse que manda — mesmo que seja mais lento do que
    o que está configurado. Quem recebe os pedidos é que sabe o que aguenta.
    """
    declared = parser.crawl_delay(user_agent)
    return float(declared) if declared is not None else None
