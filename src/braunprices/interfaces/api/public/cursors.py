"""Codificação do cursor de paginação.

O cursor é opaco de propósito: quem o recebe não deve construir um à mão nem contar com
o seu formato, porque isso transformaria um detalhe interno em contrato público. Base64
não é segurança nenhuma — é sinalização de que aquilo não é para ser lido.

Um cursor inválido é um erro do pedido (400), e nunca uma página vazia devolvida em
silêncio: devolver "não há nada" a quem pediu mal é esconder-lhe o engano.
"""

import binascii
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from decimal import Decimal, InvalidOperation

from braunprices.domain.errors import DomainError
from braunprices.domain.model.availability import Availability
from braunprices.domain.value_objects.currency import Currency
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observation_cursor import ObservationCursor
from braunprices.domain.value_objects.observed_at import ObservedAt

_SEPARATOR = "|"
_FIELDS = 4


class InvalidCursorError(Exception):
    """O cursor recebido não descreve uma posição legível."""


def encode(cursor: ObservationCursor) -> str:
    """Escreve a posição como texto opaco."""
    raw = _SEPARATOR.join(
        (
            cursor.observed_at.instant.isoformat(),
            str(cursor.price.amount),
            cursor.price.currency.code,
            cursor.availability.value,
        )
    )
    return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode(value: str) -> ObservationCursor:
    """Lê a posição a partir do texto opaco, ou recusa-a."""
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = urlsafe_b64decode(padded.encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise InvalidCursorError(_REFUSAL) from error

    parts = raw.split(_SEPARATOR)
    if len(parts) != _FIELDS:
        raise InvalidCursorError(_REFUSAL)

    instant, amount, currency, availability = parts
    try:
        return ObservationCursor(
            observed_at=ObservedAt(datetime.fromisoformat(instant)),
            price=Money.of(Decimal(amount), Currency.of(currency)),
            availability=Availability(availability),
        )
    except (ValueError, InvalidOperation, DomainError) as error:
        raise InvalidCursorError(_REFUSAL) from error


_REFUSAL = (
    "O cursor não é legível. Usa o valor de `cursor_seguinte` devolvido na página "
    "anterior, tal como veio — o formato é interno e pode mudar."
)
