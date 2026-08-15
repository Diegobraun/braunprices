"""A loja e a política com que se lhe fazem pedidos."""

from dataclasses import dataclass, field

from braunprices.domain.errors import DomainError
from braunprices.domain.value_objects.store_slug import StoreSlug

# Tetos acima dos quais deixa de ser recolha e passa a ser carga sobre a loja.
MAX_REQUESTS_PER_SECOND = 5.0
MAX_CONCURRENCY = 4


class InvalidRateLimitPolicyError(DomainError):
    """A política de rate limit pedida não é conservadora nem coerente."""


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Ritmo máximo a que esta loja é visitada.

    Os valores por omissão são deliberadamente lentos. Uma passagem diária que demore
    horas é aceitável; uma que a loja registe como pico de tráfego não é.
    """

    requests_per_second: float = 0.5
    max_concurrency: int = 1
    timeout_seconds: float = 20.0
    max_retries: int = 3
    backoff_base_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not 0 < self.requests_per_second <= MAX_REQUESTS_PER_SECOND:
            raise InvalidRateLimitPolicyError(
                f"requests_per_second={self.requests_per_second} fora do intervalo aceite "
                f"(0, {MAX_REQUESTS_PER_SECOND}]. Acima disto não é recolha, é carga."
            )
        if not 1 <= self.max_concurrency <= MAX_CONCURRENCY:
            raise InvalidRateLimitPolicyError(
                f"max_concurrency={self.max_concurrency} fora do intervalo aceite "
                f"[1, {MAX_CONCURRENCY}]."
            )
        if self.timeout_seconds <= 0:
            raise InvalidRateLimitPolicyError("timeout_seconds tem de ser positivo.")
        if self.max_retries < 0:
            raise InvalidRateLimitPolicyError("max_retries não pode ser negativo.")
        if self.backoff_base_seconds < 1:
            raise InvalidRateLimitPolicyError(
                "backoff_base_seconds abaixo de 1 não produz recuo exponencial."
            )

    @property
    def min_interval_seconds(self) -> float:
        """Intervalo mínimo entre dois pedidos consecutivos ao mesmo domínio."""
        return 1.0 / self.requests_per_second


@dataclass(frozen=True, slots=True)
class Store:
    """Loja online de onde se observam preços."""

    slug: StoreSlug
    name: str
    base_domain: str
    rate_limit: RateLimitPolicy = field(default_factory=RateLimitPolicy)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainError("A loja precisa de um nome.")
        domain = self.base_domain.strip().lower()
        if not domain or "/" in domain or " " in domain:
            raise DomainError(
                f"base_domain={self.base_domain!r} deve ser apenas o domínio, sem "
                f"esquema nem caminho."
            )
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "base_domain", domain)
