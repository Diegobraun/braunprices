"""A regra dos 30 dias do Decreto-Lei n.º 109-G/2021.

Duas perguntas diferentes, duas funções diferentes:

``lowest_price_in_window``
    Qual foi o preço mais baixo praticado na janela? É um mínimo, e só isso.

``reference_price_for_announcement``
    Que número é que a loja tem de indicar ao anunciar a redução? Normalmente é o
    mínimo acima, mas o n.º 5 do artigo prevê um caso em que não é: quando a redução
    foi sendo progressivamente aumentada, o preço de referência é o preço **anterior à
    primeira redução**, e não o mais baixo já atingido.

Separar as duas é deliberado. Uma única função que devolvesse ora um ora outro conforme
o feitio dos dados seria imprevisível no sítio onde a previsibilidade é o produto — e o
erro que produzisse seria um erro legal, não um bug de apresentação.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise

from braunprices.domain.errors import CurrencyMismatchError
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.price_window import DEFAULT_WINDOW_DAYS, PriceWindow
from braunprices.domain.value_objects.money import Money

# Uma redução "progressivamente aumentada" pressupõe mais do que uma descida: com uma
# única descida não há progressão nenhuma, e vale a regra geral.
_MIN_SUCCESSIVE_REDUCTIONS = 2


class ReferenceBasis(StrEnum):
    """Que regra produziu o preço de referência.

    Existe para que a resposta possa ser justificada e não apenas dada. Um número sem a
    regra que o gerou não é verificável por quem o lê.
    """

    LOWEST_IN_WINDOW = "lowest_in_window"
    BEFORE_PROGRESSIVE_REDUCTION = "before_progressive_reduction"


@dataclass(frozen=True, slots=True)
class ReferencePrice:
    """O preço a indicar num anúncio de redução, e a razão pela qual é esse."""

    price: Money
    basis: ReferenceBasis
    window: PriceWindow
    observations_considered: int


def observations_in_window(
    observations: Iterable[PriceObservation],
    window: PriceWindow,
) -> list[PriceObservation]:
    """Filtra as observações elegíveis e ordena-as por instante crescente.

    Elegível significa duas coisas: cair dentro da janela pelo dia de Lisboa, e ter
    sido observada num estado de disponibilidade em que o preço era efetivamente
    praticável. Um preço apresentado em produto esgotado não é um preço a que alguém
    pudesse comprar.

    Não há interpolação. Dias sem observação continuam sem observação — o histórico é
    discreto e afirma apenas o que foi visto. Inventar o valor de um dia em falta seria
    fabricar exatamente o tipo de facto que este sistema existe para verificar.
    """
    eligible = [
        observation
        for observation in observations
        if window.contains(observation.local_date) and observation.counts_as_price_practised
    ]
    eligible.sort(key=lambda observation: observation.observed_at.instant)
    _require_single_currency(eligible)
    return eligible


def lowest_price_in_window(
    observations: Sequence[PriceObservation],
    reference_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Money | None:
    """Preço mais baixo efetivamente praticado na janela anterior a ``reference_date``.

    Devolve ``None`` quando não há nenhuma observação elegível na janela. ``None``
    significa "não sabemos", e é diferente de zero: um produto sobre o qual não temos
    dados não esteve a custar nada.

    Períodos de saldos ou promoções anteriores contam como qualquer outro dia — a lei é
    explícita nisso, e é o ponto todo da norma.
    """
    window = PriceWindow(reference_date=reference_date, window_days=window_days)
    eligible = observations_in_window(observations, window)
    if not eligible:
        return None
    return min(observation.price for observation in eligible)


def reference_price_for_announcement(
    observations: Sequence[PriceObservation],
    reference_date: date,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> ReferencePrice | None:
    """Preço de referência a indicar ao anunciar uma redução nesta data.

    Aplica a regra geral — o mínimo da janela — exceto quando toda a série observada na
    janela é uma descida contínua com pelo menos duas reduções sucessivas. Nesse caso
    aplica-se o n.º 5 do artigo e o preço de referência é o que vigorava antes da
    primeira redução.

    A condição é estreita de propósito: exige que **não tenha havido qualquer subida**
    dentro da janela. Uma subida no meio significa que o preço foi reposto e que a
    campanha não é contínua, e aí a regra geral volta a ser a aplicável. Interpretar de
    forma mais larga permitiria indicar como referência um preço mais alto do que o
    consumidor chegou a ver, que é o abuso que a norma quer impedir.
    """
    window = PriceWindow(reference_date=reference_date, window_days=window_days)
    eligible = observations_in_window(observations, window)
    if not eligible:
        return None

    steps = _price_steps(eligible)
    if _is_uninterrupted_progressive_reduction(steps):
        return ReferencePrice(
            price=steps[0],
            basis=ReferenceBasis.BEFORE_PROGRESSIVE_REDUCTION,
            window=window,
            observations_considered=len(eligible),
        )

    return ReferencePrice(
        price=min(observation.price for observation in eligible),
        basis=ReferenceBasis.LOWEST_IN_WINDOW,
        window=window,
        observations_considered=len(eligible),
    )


def _price_steps(eligible: Sequence[PriceObservation]) -> list[Money]:
    """Reduz a série a mudanças de preço, colapsando repetições consecutivas.

    A recolha é diária e o preço costuma manter-se, pelo que a série crua é sobretudo
    repetição. O que interessa para detetar uma descida contínua são os degraus, não
    quantos dias cada degrau durou.
    """
    steps: list[Money] = []
    for observation in eligible:
        if not steps or steps[-1] != observation.price:
            steps.append(observation.price)
    return steps


def _is_uninterrupted_progressive_reduction(steps: Sequence[Money]) -> bool:
    """Indica se os degraus formam uma descida contínua com reduções suficientes."""
    if len(steps) < _MIN_SUCCESSIVE_REDUCTIONS + 1:
        return False
    return all(earlier > later for earlier, later in pairwise(steps))


def _require_single_currency(eligible: Sequence[PriceObservation]) -> None:
    """Recusa comparar preços de moedas diferentes na mesma série.

    Não deve acontecer — uma referência de loja tem uma moeda — mas se acontecer, a
    resposta correta é falhar de forma ruidosa, não escolher um mínimo sem significado.
    """
    currencies = {observation.price.currency for observation in eligible}
    if len(currencies) > 1:
        names = sorted(currency.code for currency in currencies)
        raise CurrencyMismatchError(
            f"A série tem observações em mais do que uma moeda ({names}) e não é comparável."
        )
