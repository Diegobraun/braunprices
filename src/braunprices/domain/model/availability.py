"""Disponibilidade de um produto no momento em que o preço foi lido.

Os valores acompanham ``schema.org/ItemAvailability``, que é a fonte primária de
extração. ``UNKNOWN`` existe para o caso em que a página não o declara — e é
tratado como "não sabemos", nunca como "estava disponível".
"""

from enum import StrEnum


class Availability(StrEnum):
    """Estado de disponibilidade observado."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PRE_ORDER = "pre_order"
    BACK_ORDER = "back_order"
    LIMITED_AVAILABILITY = "limited_availability"
    DISCONTINUED = "discontinued"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"

    @property
    def counts_as_price_practised(self) -> bool:
        """Indica se um preço observado neste estado conta como preço praticado.

        Um preço apresentado em produto esgotado não é um preço a que alguém pudesse
        comprar, e por isso não entra no cálculo da janela de 30 dias.

        ``UNKNOWN`` **não** conta. É a escolha conservadora: contar uma observação cuja
        disponibilidade não conseguimos ler seria afirmar um facto que não observámos.
        O custo é real — se uma loja não declarar disponibilidade, a sua série fica
        vazia — e é por isso que a Fase 4 tem de medir a fração de ``UNKNOWN``.
        """
        return self in _COUNTS_AS_PRACTISED


_COUNTS_AS_PRACTISED = frozenset(
    {
        Availability.IN_STOCK,
        Availability.LIMITED_AVAILABILITY,
        Availability.PRE_ORDER,
        Availability.BACK_ORDER,
    }
)
