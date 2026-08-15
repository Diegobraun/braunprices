"""A montagem das peças: onde uma regra de recolha se pode perder em silêncio.

Nada aqui toca na rede nem na base de dados — ``create_engine`` é preguiçoso e nenhum
pedido é feito.
"""

import httpx
import pytest

from braunprices.domain.model.store import Store
from braunprices.domain.value_objects.store_slug import StoreSlug
from braunprices.infrastructure.composition import (
    SCRAPERS,
    Container,
    NoScraperForStoreError,
    build_container,
)
from braunprices.infrastructure.config import Settings
from braunprices.infrastructure.scraping.http_client import CollectionHttpClient
from braunprices.infrastructure.scraping.rate_limiter import DomainRateLimiter
from braunprices.infrastructure.scraping.robots import RobotsPolicy
from braunprices.infrastructure.scraping.worten import WORTEN_SLUG, WortenScraper

USER_AGENT = "BraunPricesBot/0.1.0 (+https://github.com/Diegobraun/braunprices)"


def a_container() -> Container:
    client = httpx.Client()
    return Container(
        settings=Settings(user_agent=USER_AGENT),
        unit_of_work=lambda: (_ for _ in ()).throw(AssertionError("não devia ser usado")),
        http_client=CollectionHttpClient(
            user_agent=USER_AGENT,
            robots=RobotsPolicy(user_agent=USER_AGENT, http_client=client),
            rate_limiter=DomainRateLimiter(),
            http_client=client,
        ),
    )


def test_a_known_store_gets_its_adapter() -> None:
    store = Store(slug=WORTEN_SLUG, name="Worten", base_domain="www.worten.pt")
    scraper = a_container().scraper_for(store)
    assert isinstance(scraper, WortenScraper)
    assert scraper.store_slug == WORTEN_SLUG


def test_a_store_without_an_adapter_fails_instead_of_collecting_nothing() -> None:
    # Uma loja registada sem adaptador é um erro de configuração. Devolver uma passagem
    # vazia e bem-sucedida esconderia dias inteiros sem histórico atrás de zeros.
    store = Store(slug=StoreSlug("loja-sem-adaptador"), name="Loja", base_domain="loja.pt")
    with pytest.raises(NoScraperForStoreError, match="Não há adaptador"):
        a_container().scraper_for(store)


def test_the_error_says_which_stores_do_have_one() -> None:
    store = Store(slug=StoreSlug("loja-sem-adaptador"), name="Loja", base_domain="loja.pt")
    with pytest.raises(NoScraperForStoreError, match="worten"):
        a_container().scraper_for(store)


def test_every_registered_adapter_answers_for_the_store_it_is_registered_under() -> None:
    # Trocar duas entradas do mapa gravaria observações de uma loja com o slug de
    # outra, e o histórico ficaria misturado sem nada rebentar.
    client = a_container().http_client
    for slug, build in SCRAPERS.items():
        store = Store(slug=slug, name=str(slug), base_domain=f"{slug}.pt")
        assert build(store, client).store_slug == slug


def test_the_assembled_client_carries_the_configured_user_agent() -> None:
    # A regra vive no código de recolha, mas é aqui que ela se aplicaria a nada se a
    # montagem passasse outra coisa.
    container = build_container(Settings(user_agent=USER_AGENT))
    assert container.http_client.user_agent == USER_AGENT
    assert "http" in container.http_client.user_agent


def test_a_user_agent_that_pretends_to_be_a_browser_is_refused_before_anything_is_built() -> None:
    with pytest.raises(ValueError, match="finge ser um browser"):
        build_container(Settings(user_agent="Mozilla/5.0 (+https://exemplo.pt)"))
