"""Cliente HTTP da recolha: identificado, lento e que aceita um não como resposta.

Três regras moldam este ficheiro, e nenhuma é negociável:

1. O user-agent é o do projeto, com URL de contacto. Nunca se finge ser um browser.
2. O ritmo é conservador e por domínio, com recuo exponencial nas falhas passageiras.
3. Perante 403, 429 ou captcha, **para-se e regista-se**. Não há aqui rotação de
   agentes, de endereços, nem qualquer outra forma de voltar a bater à porta com outra
   cara. Contornar um bloqueio é uma decisão de negócio e legal, e não pertence a este
   ficheiro.
"""

from dataclasses import dataclass

import httpx
import structlog

from braunprices.domain.model.scrape_outcome import FailureReason, ScrapeFailure
from braunprices.domain.model.store import RateLimitPolicy
from braunprices.infrastructure.scraping.rate_limiter import (
    DomainRateLimiter,
    exponential_backoff_seconds,
)
from braunprices.infrastructure.scraping.robots import RobotsPolicy

logger = structlog.get_logger(__name__)

# Códigos em que a loja está a dizer não a quem pede, e não a dar um erro passageiro.
BLOCKING_STATUS_CODES = frozenset({401, 403, 429, 451})

# Sinais de que a resposta é uma parede de verificação em vez da página pedida. Uma
# página de captcha devolve 200, e sem isto seria lida como marcação em falta — o que
# mandaria alguém investigar o adaptador em vez de perceber que a loja travou.
CAPTCHA_MARKERS = (
    "captcha",
    "cf-browser-verification",
    "challenge-platform",
    "px-captcha",
    "are you a robot",
    "verifica que não és um robô",
)


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """Uma página obtida com sucesso."""

    url: str
    html: str
    status_code: int


class CollectionHttpClient:
    """Faz pedidos de recolha respeitando robots.txt e o ritmo de cada loja."""

    def __init__(
        self,
        user_agent: str,
        robots: RobotsPolicy,
        rate_limiter: DomainRateLimiter,
        http_client: httpx.Client,
    ) -> None:
        self._user_agent = user_agent
        self._robots = robots
        self._rate_limiter = rate_limiter
        self._http = http_client

    def get(self, url: str, policy: RateLimitPolicy) -> FetchedPage | ScrapeFailure:
        """Obtém uma página, ou explica por que não a obteve."""
        decision = self._robots.is_allowed(url)
        if not decision.is_allowed:
            logger.info("recolha.proibida_por_robots", url=url, motivo=decision.reason)
            return ScrapeFailure(reason=FailureReason.DISALLOWED_BY_ROBOTS, detail=decision.reason)

        domain = httpx.URL(url).host
        # Quando a loja declara um Crawl-delay, é esse que manda, mesmo que seja mais
        # lento do que o configurado: quem recebe os pedidos é que sabe o que aguenta.
        interval = max(policy.min_interval_seconds, decision.crawl_delay_seconds or 0.0)

        last_failure: ScrapeFailure | None = None
        for attempt in range(1, policy.max_retries + 2):
            self._rate_limiter.wait_for_turn(domain, interval)
            outcome = self._attempt(url, policy)
            if isinstance(outcome, FetchedPage):
                return outcome

            last_failure = outcome
            if outcome.should_stop_collecting_from_this_store:
                return outcome
            if outcome.reason in {FailureReason.NOT_FOUND, FailureReason.MARKUP_INVALID}:
                return outcome
            if attempt <= policy.max_retries:
                pause = exponential_backoff_seconds(attempt, policy.backoff_base_seconds)
                logger.info(
                    "recolha.nova_tentativa",
                    url=url,
                    tentativa=attempt,
                    espera_segundos=pause,
                    motivo=outcome.reason.value,
                )
                self._rate_limiter.back_off(domain, pause)

        return last_failure or ScrapeFailure(
            reason=FailureReason.NETWORK_ERROR,
            detail="Sem tentativas realizadas.",
        )

    def _attempt(self, url: str, policy: RateLimitPolicy) -> FetchedPage | ScrapeFailure:
        try:
            response = self._http.get(
                url,
                headers={"User-Agent": self._user_agent},
                timeout=policy.timeout_seconds,
                follow_redirects=True,
            )
        except httpx.TimeoutException as error:
            return ScrapeFailure(reason=FailureReason.TIMEOUT, detail=str(error))
        except httpx.HTTPError as error:
            return ScrapeFailure(reason=FailureReason.NETWORK_ERROR, detail=str(error))

        return self._classify(url, response)

    def _classify(self, url: str, response: httpx.Response) -> FetchedPage | ScrapeFailure:
        if response.status_code in BLOCKING_STATUS_CODES:
            logger.warning("recolha.bloqueada", url=url, status=response.status_code)
            return ScrapeFailure(
                reason=FailureReason.BLOCKED,
                detail=(
                    f"A loja respondeu {response.status_code}. A recolha para aqui e fica "
                    f"registada. Contornar o bloqueio não é uma opção deste projeto."
                ),
                http_status=response.status_code,
            )

        if response.status_code == httpx.codes.NOT_FOUND:
            return ScrapeFailure(
                reason=FailureReason.NOT_FOUND,
                detail="A página de produto já não existe.",
                http_status=response.status_code,
            )

        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            return ScrapeFailure(
                reason=FailureReason.SERVER_ERROR,
                detail=f"A loja respondeu {response.status_code}.",
                http_status=response.status_code,
            )

        if response.status_code >= httpx.codes.BAD_REQUEST:
            return ScrapeFailure(
                reason=FailureReason.MARKUP_INVALID,
                detail=f"Resposta inesperada {response.status_code}.",
                http_status=response.status_code,
            )

        html = response.text
        if _looks_like_a_challenge(html):
            logger.warning("recolha.desafio_de_verificacao", url=url)
            return ScrapeFailure(
                reason=FailureReason.BLOCKED,
                detail=(
                    "A resposta é uma página de verificação, não a página de produto. "
                    "A recolha para aqui e fica registada."
                ),
                http_status=response.status_code,
            )

        return FetchedPage(url=str(response.url), html=html, status_code=response.status_code)


def _looks_like_a_challenge(html: str) -> bool:
    """Deteta uma página de verificação servida com 200.

    Só olha para o início do documento: um catálogo pode mencionar a palavra "captcha"
    numa descrição de produto, e varrer a página inteira daria falsos positivos que
    parariam a recolha sem motivo.
    """
    head = html[:4096].lower()
    return any(marker in head for marker in CAPTCHA_MARKERS)
