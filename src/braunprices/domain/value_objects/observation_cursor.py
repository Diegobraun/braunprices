"""A posição a partir da qual continuar a ler um histórico.

Paginar por deslocamento (``OFFSET``) numa série a que se acrescentam factos é uma
forma discreta de mentir: entre a página 1 e a página 2 entram observações novas, e o
leitor recebe repetições ou saltos sem nada lhe dizer que isso aconteceu. Num sistema
cujo produto é a fidelidade do histórico, isso não é um detalhe de paginação.

Por isso a posição é o último facto lido, e não quantos ficaram para trás. O histórico
é append-only e ordenado pelo instante observado, o que torna esta posição estável para
sempre: a página seguinte é sempre "o que vem depois disto", independentemente do que
tenha entrado entretanto.

O par instante/preço não chega para desempatar sozinho — a mesma referência pode ter
duas observações no mesmo instante com preços diferentes — e por isso a posição inclui
os três campos que a chave natural do facto diário usa para o distinguir.
"""

from dataclasses import dataclass

from braunprices.domain.model.availability import Availability
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observed_at import ObservedAt


@dataclass(frozen=True, slots=True)
class ObservationCursor:
    """O último facto lido, que é por onde a leitura continua."""

    observed_at: ObservedAt
    price: Money
    availability: Availability

    @classmethod
    def after(cls, observation: PriceObservation) -> "ObservationCursor":
        """Posição imediatamente a seguir a esta observação."""
        return cls(
            observed_at=observation.observed_at,
            price=observation.price,
            availability=observation.availability,
        )
