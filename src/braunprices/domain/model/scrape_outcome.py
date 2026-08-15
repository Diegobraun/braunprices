"""O resultado de tentar observar o preço de uma referência de loja.

Uma tentativa tem dois desfechos possíveis, e ambos interessam. Uma observação
bem-sucedida acrescenta um facto ao histórico. Uma falha **também é informação**: é
assim que se descobre que uma loja mudou a marcação e que a recolha está a degradar-se
em silêncio, que é a falha mais cara que este sistema pode ter.

Por isso a falha não é uma exceção que se apanha e deita fora: é um valor, com motivo
classificado, que a passagem diária conta e regista.
"""

from dataclasses import dataclass
from enum import StrEnum

from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.value_objects.ean import EAN


class ExtractionSource(StrEnum):
    """De onde saiu o preço.

    Distinguir as duas fontes é o que permite medir a degradação: uma loja que passa
    de ``JSON_LD`` para ``HTML_FALLBACK`` continua a devolver preços, e sem esta
    distinção ninguém daria por isso até a marcação desaparecer de vez.
    """

    JSON_LD = "json_ld"
    HTML_FALLBACK = "html_fallback"


class FailureReason(StrEnum):
    """Por que motivo não foi possível observar o preço."""

    DISALLOWED_BY_ROBOTS = "disallowed_by_robots"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    MARKUP_MISSING = "markup_missing"
    MARKUP_INVALID = "markup_invalid"
    MARKUP_AMBIGUOUS = "markup_ambiguous"
    PRICE_UNREADABLE = "price_unreadable"

    @property
    def is_the_store_saying_no(self) -> bool:
        """Indica se a loja recusou o acesso, em vez de a página ter mudado.

        A distinção decide o que fazer a seguir: perante uma recusa, para-se e
        regista-se — nunca se tenta outra forma de entrar. Perante marcação mudada,
        há trabalho de manutenção a fazer no adaptador.
        """
        return self in {FailureReason.DISALLOWED_BY_ROBOTS, FailureReason.BLOCKED}


@dataclass(frozen=True, slots=True)
class ScrapedListing:
    """Uma observação de preço bem-sucedida, com o que mais a página revelou.

    ``product_name`` e ``ean`` vêm da página e servem para manter o produto atualizado
    e para o casamento entre lojas. Não fazem parte da observação de preço, que é
    imutável: se o nome do produto mudar amanhã, o preço de hoje continua a ser o que
    foi.
    """

    observation: PriceObservation
    product_name: str
    ean: EAN | None
    source: ExtractionSource


@dataclass(frozen=True, slots=True)
class ScrapeFailure:
    """Uma tentativa que não produziu observação, com o motivo classificado.

    ``detail`` é para humanos e aparece no registo. ``http_status`` é ``None`` quando
    a falha aconteceu antes de haver resposta, ou depois de a haver e a página estar
    apenas diferente do esperado.
    """

    reason: FailureReason
    detail: str
    http_status: int | None = None

    @property
    def should_stop_collecting_from_this_store(self) -> bool:
        """Indica se esta falha manda parar a recolha desta loja, e não só desta página.

        Uma loja que bloqueia não bloqueia uma página: bloqueia quem está a pedir.
        Continuar a percorrer o catálogo depois de um 429 é transformar um aviso num
        problema.
        """
        return self.reason.is_the_store_saying_no


ScrapeOutcome = ScrapedListing | ScrapeFailure
