"""Erros de domínio.

Todos herdam de :class:`DomainError`, para que uma camada de fronteira possa
distinguir "os dados violam uma invariante do domínio" de "a infraestrutura falhou"
sem apanhar exceções a mais.
"""


class DomainError(Exception):
    """Base de todos os erros de domínio."""


class InvalidEANError(DomainError):
    """O identificador não é um EAN/UPC válido."""


class InvalidMoneyError(DomainError):
    """O valor monetário não é representável nos termos deste domínio."""


class CurrencyMismatchError(DomainError):
    """Tentativa de comparar ou combinar montantes em moedas diferentes."""


class UnknownCurrencyError(DomainError):
    """A moeda não consta da tabela de moedas conhecidas."""


class InvalidStoreSlugError(DomainError):
    """O identificador de loja não respeita o formato estável exigido."""


class InvalidObservedAtError(DomainError):
    """O instante de observação não é utilizável como carimbo temporal."""


class InvalidPriceWindowError(DomainError):
    """A janela de observação pedida não é válida."""


class ListingNotInProductError(DomainError):
    """A referência de loja indicada não pertence a este produto."""
