"""O preço de referência a indicar num anúncio de redução.

Cobre o n.º 5 do artigo: quando a redução foi sendo progressivamente aumentada, o
preço de referência é o anterior à primeira redução, e não o mais baixo já atingido.
É o caso onde as implementações ingénuas falham, porque devolvem o mínimo.
"""

from datetime import date

from braunprices.domain.model.availability import Availability
from braunprices.domain.rules.price_reference import (
    ReferenceBasis,
    lowest_price_in_window,
    reference_price_for_announcement,
)
from braunprices.domain.value_objects.money import Money
from tests.unit.domain.conftest import observation

REFERENCE = date(2026, 7, 12)


def test_returns_none_when_there_is_nothing_to_go_on() -> None:
    assert reference_price_for_announcement([], REFERENCE) is None


# -- regra geral -----------------------------------------------------------


def test_a_stable_price_is_its_own_reference() -> None:
    series = [observation(day=f"2026-06-{day:02d}", price="59.99") for day in range(12, 31)]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("59.99")
    assert result.basis is ReferenceBasis.LOWEST_IN_WINDOW


def test_a_price_that_went_up_and_down_uses_the_lowest() -> None:
    series = [
        observation(day="2026-06-20", price="100.00"),
        observation(day="2026-06-24", price="60.00"),
        observation(day="2026-06-28", price="100.00"),
        observation(day="2026-07-05", price="90.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("60.00")
    assert result.basis is ReferenceBasis.LOWEST_IN_WINDOW


def test_a_single_reduction_is_not_a_progressive_one() -> None:
    # Uma só descida não é uma redução "progressivamente aumentada": vale a regra
    # geral, e o preço mais baixo praticado é o de agora.
    series = [
        observation(day="2026-06-20", price="100.00"),
        observation(day="2026-07-01", price="90.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("90.00")
    assert result.basis is ReferenceBasis.LOWEST_IN_WINDOW


# -- n.º 5: redução progressiva --------------------------------------------


def test_an_uninterrupted_gradual_decline_references_the_price_before_the_first_cut() -> None:
    # O caso que a especificação assinala como o que mais falha. O mínimo da janela
    # é 70 €, mas o número que a loja tem de indicar é 100 €: o preço que vigorava
    # antes de a campanha começar.
    series = [
        observation(day="2026-06-15", price="100.00"),
        observation(day="2026-06-22", price="90.00"),
        observation(day="2026-06-29", price="80.00"),
        observation(day="2026-07-06", price="70.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("100.00")
    assert result.basis is ReferenceBasis.BEFORE_PROGRESSIVE_REDUCTION
    assert lowest_price_in_window(series, REFERENCE) == Money.of("70.00")


def test_repeated_daily_observations_do_not_break_the_decline() -> None:
    # A recolha é diária e o preço repete-se entre degraus. Se a monotonia fosse
    # avaliada sobre a série crua, a igualdade entre dias consecutivos partiria a
    # cadeia e o n.º 5 nunca seria detetado em dados reais.
    series = (
        [observation(day=f"2026-06-{day:02d}", price="100.00") for day in range(15, 22)]
        + [observation(day=f"2026-06-{day:02d}", price="90.00") for day in range(22, 29)]
        + [observation(day=f"2026-06-{day:02d}", price="80.00") for day in range(29, 31)]
        + [observation(day=f"2026-07-{day:02d}", price="70.00") for day in range(1, 12)]
    )
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("100.00")
    assert result.basis is ReferenceBasis.BEFORE_PROGRESSIVE_REDUCTION


def test_three_steps_are_enough_for_the_rule_to_apply() -> None:
    series = [
        observation(day="2026-06-20", price="100.00"),
        observation(day="2026-06-25", price="90.00"),
        observation(day="2026-07-01", price="80.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("100.00")
    assert result.basis is ReferenceBasis.BEFORE_PROGRESSIVE_REDUCTION


def test_a_rise_in_the_middle_interrupts_the_campaign_and_restores_the_general_rule() -> None:
    # Houve reposição de preço: a campanha não é contínua. Aplicar o n.º 5 aqui
    # permitiria anunciar como referência 120 €, mais alto do que o consumidor viu
    # em 80 € dentro da mesma janela — que é o abuso que a norma quer impedir.
    series = [
        observation(day="2026-06-15", price="100.00"),
        observation(day="2026-06-18", price="80.00"),
        observation(day="2026-06-25", price="120.00"),
        observation(day="2026-07-01", price="110.00"),
        observation(day="2026-07-08", price="100.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("80.00")
    assert result.basis is ReferenceBasis.LOWEST_IN_WINDOW


def test_a_decline_that_ends_with_a_rise_is_not_progressive() -> None:
    series = [
        observation(day="2026-06-15", price="100.00"),
        observation(day="2026-06-20", price="90.00"),
        observation(day="2026-06-25", price="80.00"),
        observation(day="2026-07-05", price="95.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("80.00")
    assert result.basis is ReferenceBasis.LOWEST_IN_WINDOW


def test_out_of_stock_days_do_not_create_a_false_decline() -> None:
    # A observação a 50 € está esgotada e não conta; a série elegível passa a ser
    # 100 -> 90, uma só redução, logo regra geral.
    series = [
        observation(day="2026-06-15", price="100.00"),
        observation(day="2026-06-20", price="90.00"),
        observation(day="2026-06-25", price="50.00", availability=Availability.OUT_OF_STOCK),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("90.00")
    assert result.basis is ReferenceBasis.LOWEST_IN_WINDOW


def test_only_the_part_of_the_decline_inside_the_window_is_considered() -> None:
    # O degrau de 200 € está fora dos 30 dias: a lei limita-se à janela, e o preço
    # de referência é o mais alto que ainda cai dentro dela.
    series = [
        observation(day="2026-05-01", price="200.00"),
        observation(day="2026-06-15", price="100.00"),
        observation(day="2026-06-22", price="90.00"),
        observation(day="2026-07-01", price="80.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("100.00")


def test_the_result_carries_the_window_and_how_many_observations_it_used() -> None:
    # Um número sem a regra e o âmbito que o geraram não é verificável por quem o lê.
    series = [
        observation(day="2026-06-20", price="100.00"),
        observation(day="2026-06-25", price="90.00"),
        observation(day="2026-07-01", price="80.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.observations_considered == 3
    assert result.window.start == date(2026, 6, 12)
    assert result.window.end_exclusive == REFERENCE


def test_the_order_of_arrival_does_not_change_the_basis() -> None:
    series = [
        observation(day="2026-07-06", price="70.00"),
        observation(day="2026-06-15", price="100.00"),
        observation(day="2026-06-29", price="80.00"),
        observation(day="2026-06-22", price="90.00"),
    ]
    result = reference_price_for_announcement(series, REFERENCE)
    assert result is not None
    assert result.price == Money.of("100.00")
    assert result.basis is ReferenceBasis.BEFORE_PROGRESSIVE_REDUCTION
