"""Política de recolha: robots.txt em runtime, ritmo conservador e parar perante um não.

Sem rede: o transporte do httpx é substituído por um que responde a partir de um mapa.
Não é um mock do que se está a testar — é o outro lado do fio, que aqui não interessa
exercitar. O que está sob teste é a decisão que se toma perante cada resposta.
"""

import httpx
import pytest

from braunprices.domain.model.scrape_outcome import FailureReason, ScrapeFailure
from braunprices.domain.model.store import RateLimitPolicy
from braunprices.infrastructure.scraping.http_client import CollectionHttpClient, FetchedPage
from braunprices.infrastructure.scraping.rate_limiter import (
    DomainRateLimiter,
    exponential_backoff_seconds,
)
from braunprices.infrastructure.scraping.robots import RobotsPolicy

USER_AGENT = "BraunPricesBot/0.1 (+https://github.com/Diegobraun/braunprices)"
PRODUCT_URL = "https://www.worten.pt/produtos/algum-produto-123"


class FakeClock:
    """Relógio controlado, para que um teste de rate limit não durma de verdade."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        """Devolve o instante atual do relógio simulado."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Regista a espera e avança o relógio, sem bloquear de verdade."""
        self.slept.append(seconds)
        self.now += seconds


def client_answering(responses: dict[str, httpx.Response]) -> httpx.Client:
    """Cliente httpx que responde a partir de um mapa de URL para resposta."""

    def handler(request: httpx.Request) -> httpx.Response:
        for url, response in responses.items():
            if str(request.url).startswith(url):
                return response
        return httpx.Response(404, text="Not found")

    return httpx.Client(transport=httpx.MockTransport(handler))


def robots_allowing_products(extra: str = "") -> httpx.Response:
    return httpx.Response(200, text=f"User-agent: *\nDisallow: /carrinho\n{extra}")


def build_client(
    responses: dict[str, httpx.Response], clock: FakeClock | None = None
) -> tuple[CollectionHttpClient, FakeClock]:
    clock = clock or FakeClock()
    http = client_answering(responses)
    return (
        CollectionHttpClient(
            user_agent=USER_AGENT,
            robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
            rate_limiter=DomainRateLimiter(monotonic=clock.monotonic, sleep=clock.sleep),
            http_client=http,
        ),
        clock,
    )


# -- robots.txt ------------------------------------------------------------


def test_a_permitted_url_is_fetched() -> None:
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": robots_allowing_products(),
            PRODUCT_URL: httpx.Response(200, text="<html>produto</html>"),
        }
    )
    page = client.get(PRODUCT_URL, RateLimitPolicy())
    assert isinstance(page, FetchedPage)
    assert page.html == "<html>produto</html>"


def test_a_disallowed_url_is_never_requested() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /produtos")
        return httpx.Response(200, text="<html>não devia chegar aqui</html>")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(),
        http_client=http,
    )

    failure = client.get(PRODUCT_URL, RateLimitPolicy())
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.DISALLOWED_BY_ROBOTS
    assert requested == ["https://www.worten.pt/robots.txt"]


def test_when_robots_cannot_be_read_the_domain_stays_off_limits() -> None:
    # Presumir permissão por não se ter conseguido perguntar é a definição prática de
    # não perguntar.
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": httpx.Response(500, text="erro"),
            PRODUCT_URL: httpx.Response(200, text="<html>produto</html>"),
        }
    )
    failure = client.get(PRODUCT_URL, RateLimitPolicy())
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.DISALLOWED_BY_ROBOTS


def test_a_store_without_robots_txt_is_treated_as_permitting() -> None:
    # 404 é a única forma de ausência que o próprio protocolo define como permissão.
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": httpx.Response(404, text=""),
            PRODUCT_URL: httpx.Response(200, text="<html>produto</html>"),
        }
    )
    assert isinstance(client.get(PRODUCT_URL, RateLimitPolicy()), FetchedPage)


def test_robots_is_read_once_per_domain_and_not_once_per_page() -> None:
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        return httpx.Response(200, text="<html>produto</html>")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(),
        http_client=http,
    )
    for page in range(3):
        client.get(f"{PRODUCT_URL}-{page}", RateLimitPolicy())

    assert hits.count("/robots.txt") == 1


def test_the_real_worten_robots_allows_product_pages(worten_robots_txt: str) -> None:
    # Contra o robots.txt real capturado. Se a Worten mudar de política, este teste
    # continua a passar contra a captura — o que muda é o runtime, e é por isso que a
    # verificação também acontece lá.
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": httpx.Response(200, text=worten_robots_txt),
            PRODUCT_URL: httpx.Response(200, text="<html>produto</html>"),
        }
    )
    assert isinstance(client.get(PRODUCT_URL, RateLimitPolicy()), FetchedPage)


def test_the_real_worten_robots_forbids_the_search_pages(worten_robots_txt: str) -> None:
    client, _ = build_client(
        {"https://www.worten.pt/robots.txt": httpx.Response(200, text=worten_robots_txt)}
    )
    failure = client.get("https://www.worten.pt/search?q=tv", RateLimitPolicy())
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.DISALLOWED_BY_ROBOTS


# -- bloqueios: parar e registar -------------------------------------------


@pytest.mark.parametrize("status", [401, 403, 429, 451])
def test_a_block_stops_the_collection_and_is_never_worked_around(status: int) -> None:
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        attempts.append(request.headers.get("user-agent", ""))
        return httpx.Response(status, text="bloqueado")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(),
        http_client=http,
    )

    failure = client.get(PRODUCT_URL, RateLimitPolicy(max_retries=3))
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.BLOCKED
    assert failure.http_status == status
    assert failure.should_stop_collecting_from_this_store is True
    # Uma só tentativa: não se insiste depois de um não, e o agente é sempre o mesmo.
    assert len(attempts) == 1
    assert set(attempts) == {USER_AGENT}


def test_a_verification_page_served_with_200_counts_as_a_block() -> None:
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": robots_allowing_products(),
            PRODUCT_URL: httpx.Response(
                200, text="<html><head><title>Checking</title></head><body>captcha</body></html>"
            ),
        }
    )
    failure = client.get(PRODUCT_URL, RateLimitPolicy())
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.BLOCKED


def test_the_word_captcha_deep_inside_a_catalogue_page_is_not_a_block() -> None:
    # Varrer a página inteira daria falsos positivos que parariam a recolha sem motivo.
    body = "<html><body>" + ("produto " * 2000) + "captcha</body></html>"
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": robots_allowing_products(),
            PRODUCT_URL: httpx.Response(200, text=body),
        }
    )
    assert isinstance(client.get(PRODUCT_URL, RateLimitPolicy()), FetchedPage)


def test_a_missing_page_is_not_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        attempts += 1
        return httpx.Response(404, text="")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(),
        http_client=http,
    )
    failure = client.get(PRODUCT_URL, RateLimitPolicy(max_retries=3))
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.NOT_FOUND
    assert attempts == 1


def test_a_server_error_is_retried_and_then_reported() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        attempts += 1
        return httpx.Response(503, text="")

    clock = FakeClock()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(monotonic=clock.monotonic, sleep=clock.sleep),
        http_client=http,
    )
    failure = client.get(PRODUCT_URL, RateLimitPolicy(max_retries=2))
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.SERVER_ERROR
    assert attempts == 3  # a primeira mais duas repetições


def test_a_transient_error_that_recovers_yields_the_page() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, text="")
        return httpx.Response(200, text="<html>produto</html>")

    clock = FakeClock()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(monotonic=clock.monotonic, sleep=clock.sleep),
        http_client=http,
    )
    assert isinstance(client.get(PRODUCT_URL, RateLimitPolicy(max_retries=2)), FetchedPage)


def test_a_network_failure_is_reported_and_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        message = "ligação recusada"
        raise httpx.ConnectError(message)

    clock = FakeClock()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(monotonic=clock.monotonic, sleep=clock.sleep),
        http_client=http,
    )
    failure = client.get(PRODUCT_URL, RateLimitPolicy(max_retries=1))
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.NETWORK_ERROR


def test_a_timeout_is_reported_as_such() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        message = "demorou de mais"
        raise httpx.ReadTimeout(message)

    clock = FakeClock()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(monotonic=clock.monotonic, sleep=clock.sleep),
        http_client=http,
    )
    failure = client.get(PRODUCT_URL, RateLimitPolicy(max_retries=0))
    assert isinstance(failure, ScrapeFailure)
    assert failure.reason is FailureReason.TIMEOUT


# -- identificação ---------------------------------------------------------


def test_the_user_agent_identifies_the_project_and_never_a_browser() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /carrinho")
        return httpx.Response(200, text="<html>produto</html>")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CollectionHttpClient(
        user_agent=USER_AGENT,
        robots=RobotsPolicy(user_agent=USER_AGENT, http_client=http),
        rate_limiter=DomainRateLimiter(),
        http_client=http,
    )
    client.get(PRODUCT_URL, RateLimitPolicy())

    assert USER_AGENT in seen
    assert "BraunPrices" in USER_AGENT
    assert "https://" in USER_AGENT  # contacto do projeto
    for agent in seen:
        assert "Mozilla" not in agent
        assert "Chrome" not in agent


# -- ritmo -----------------------------------------------------------------


def test_consecutive_requests_to_a_domain_are_spaced_out() -> None:
    clock = FakeClock()
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": robots_allowing_products(),
            "https://www.worten.pt/produtos/": httpx.Response(200, text="<html>ok</html>"),
        },
        clock,
    )
    policy = RateLimitPolicy(requests_per_second=0.5)  # dois segundos entre pedidos

    for page in range(3):
        client.get(f"https://www.worten.pt/produtos/p{page}", policy)

    assert clock.slept == [pytest.approx(2.0), pytest.approx(2.0)]


def test_a_crawl_delay_declared_by_the_store_wins_over_the_configured_pace() -> None:
    # Quem recebe os pedidos é que sabe o que aguenta.
    clock = FakeClock()
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": robots_allowing_products("Crawl-delay: 10"),
            "https://www.worten.pt/produtos/": httpx.Response(200, text="<html>ok</html>"),
        },
        clock,
    )
    policy = RateLimitPolicy(requests_per_second=5)  # 0,2 s configurados

    client.get("https://www.worten.pt/produtos/p0", policy)
    client.get("https://www.worten.pt/produtos/p1", policy)

    assert clock.slept == [pytest.approx(10.0)]


def test_different_domains_do_not_wait_for_each_other() -> None:
    clock = FakeClock()
    client, _ = build_client(
        {
            "https://www.worten.pt/robots.txt": robots_allowing_products(),
            "https://www.worten.pt/produtos/": httpx.Response(200, text="<html>ok</html>"),
            "https://outra-loja.pt/robots.txt": robots_allowing_products(),
            "https://outra-loja.pt/produtos/": httpx.Response(200, text="<html>ok</html>"),
        },
        clock,
    )
    policy = RateLimitPolicy(requests_per_second=0.5)

    client.get("https://www.worten.pt/produtos/p0", policy)
    client.get("https://outra-loja.pt/produtos/p0", policy)

    assert clock.slept == []


def test_the_backoff_grows_between_attempts() -> None:
    assert exponential_backoff_seconds(1, 2.0) == 2.0
    assert exponential_backoff_seconds(2, 2.0) == 4.0
    assert exponential_backoff_seconds(3, 2.0) == 8.0


def test_the_backoff_still_grows_when_the_base_is_one() -> None:
    assert exponential_backoff_seconds(1, 1.0) == 1.0
    assert exponential_backoff_seconds(3, 1.0) == 3.0


def test_the_attempt_count_starts_at_one() -> None:
    with pytest.raises(ValueError, match="começa em 1"):
        exponential_backoff_seconds(0, 2.0)


def test_backing_off_a_domain_delays_its_next_turn() -> None:
    clock = FakeClock()
    limiter = DomainRateLimiter(monotonic=clock.monotonic, sleep=clock.sleep)
    limiter.back_off("www.worten.pt", 30.0)
    assert limiter.wait_for_turn("www.worten.pt", 2.0) == pytest.approx(30.0)
