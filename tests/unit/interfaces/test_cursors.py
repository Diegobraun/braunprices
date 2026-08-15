"""O cursor de paginação: ida e volta, e recusa de tudo o resto."""

from base64 import urlsafe_b64encode
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from braunprices.domain.model.availability import Availability
from braunprices.domain.value_objects.money import Money
from braunprices.domain.value_objects.observation_cursor import ObservationCursor
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.interfaces.api.public import cursors

A_POSITION = ObservationCursor(
    observed_at=ObservedAt(datetime(2026, 7, 4, 8, 30, tzinfo=UTC)),
    price=Money.of(Decimal("59.99")),
    availability=Availability.IN_STOCK,
)


def test_a_position_survives_the_round_trip() -> None:
    assert cursors.decode(cursors.encode(A_POSITION)) == A_POSITION


def test_the_cursor_does_not_show_what_it_carries() -> None:
    # Opaco por desenho: quem o lê não deve construir um à mão, porque isso
    # transformaria um detalhe interno em contrato público.
    encoded = cursors.encode(A_POSITION)
    assert "59.99" not in encoded
    assert "2026" not in encoded


def test_the_price_survives_with_the_scale_it_had() -> None:
    # 59.90 e 59.9 são o mesmo número e não são o mesmo preço: a escala é a da moeda.
    position = ObservationCursor(
        observed_at=A_POSITION.observed_at,
        price=Money.of(Decimal("59.90")),
        availability=Availability.IN_STOCK,
    )
    assert str(cursors.decode(cursors.encode(position)).price.amount) == "59.90"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "isto-nao-e-base64!!",
        "YWJj",  # base64 legítimo, conteúdo que não é uma posição
        "MjAyNi0wNy0wNFQwODozMDowMCswMDowMHw1OS45OXxFVVI=",  # falta a disponibilidade
    ],
)
def test_anything_that_is_not_a_position_is_refused(value: str) -> None:
    # Recusar é o ponto: devolver a primeira página a quem pediu mal esconde-lhe o
    # engano, e quem estiver a percorrer o histórico volta ao início sem saber porquê.
    with pytest.raises(cursors.InvalidCursorError):
        cursors.decode(value)


def test_a_position_with_an_unknown_currency_is_refused() -> None:
    forged = urlsafe_b64encode(b"2026-07-04T08:30:00+00:00|59.99|XPTO|in_stock").decode()
    with pytest.raises(cursors.InvalidCursorError):
        cursors.decode(forged)


def test_a_position_with_an_unknown_availability_is_refused() -> None:
    forged = urlsafe_b64encode(b"2026-07-04T08:30:00+00:00|59.99|EUR|talvez").decode()
    with pytest.raises(cursors.InvalidCursorError):
        cursors.decode(forged)


def test_the_refusal_says_where_a_good_cursor_comes_from() -> None:
    with pytest.raises(cursors.InvalidCursorError, match="cursor_seguinte"):
        cursors.decode("lixo")
