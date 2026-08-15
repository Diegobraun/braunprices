"""Porto de recolha, definido pelo domínio e implementado por um adaptador por loja."""

from typing import Protocol

from braunprices.domain.model.product import StoreListing
from braunprices.domain.model.scrape_outcome import ScrapeOutcome
from braunprices.domain.value_objects.store_slug import StoreSlug


class StoreScraper(Protocol):
    """Sabe observar o preço de uma referência numa loja concreta.

    Nunca levanta exceção por a loja ter respondido mal. Uma página que mudou, uma
    loja que bloqueou ou um pedido que expirou são desfechos previstos, e voltam como
    ``ScrapeFailure`` para poderem ser contados. Exceção fica reservada para o que é
    de facto imprevisto.
    """

    @property
    def store_slug(self) -> StoreSlug:
        """A loja que este adaptador sabe ler."""
        ...

    def fetch(self, listing: StoreListing) -> ScrapeOutcome:
        """Observa o preço desta referência agora.

        Antes de pedir a página, verifica o ``robots.txt`` da loja em runtime e
        respeita o rate limit configurado.
        """
        ...
