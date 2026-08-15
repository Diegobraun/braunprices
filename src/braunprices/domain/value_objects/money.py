"""Montante monetário.

``Decimal`` sempre. ``float`` para dinheiro é bug, não estilo: 0.1 + 0.2 não é 0.3 em
binário, e um histórico de preços que acumula esse erro deixa de servir para provar
seja o que for.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from braunprices.domain.errors import CurrencyMismatchError, InvalidMoneyError
from braunprices.domain.value_objects.currency import EUR, Currency

# Espaços que aparecem em páginas portuguesas entre o número e o símbolo, ou como
# separador de milhares. O não separável (U+00A0) é o mais comum e é invisível na
# inspeção visual do HTML, o que o torna a causa clássica de parsing que "devia
# funcionar".
_SPACE_CHARACTERS: Final[str] = (
    "\u0020"  # espaço
    "\u00a0"  # não separável
    "\u202f"  # não separável estreito
    "\u2007"  # espaço de algarismo
    "\u2009"  # espaço fino
    "\u2060"  # word joiner
)

_CURRENCY_SYMBOLS: Final[dict[str, Currency]] = {"€": EUR, "EUR": EUR}

_INTEGER_GROUPED: Final[re.Pattern[str]] = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_INTEGER_PLAIN: Final[re.Pattern[str]] = re.compile(r"^\d+$")
_DECIMALS: Final[re.Pattern[str]] = re.compile(r"^\d+$")


@dataclass(frozen=True, slots=True)
class Money:
    """Montante não negativo numa moeda, com a escala exata da unidade menor.

    Dois montantes são iguais quando o valor e a moeda coincidem. ``59`` e ``59.00``
    em euros são o mesmo montante: a construção normaliza a escala, para que a
    igualdade não dependa de como o preço veio escrito na página.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):  # pragma: no cover - guarda de tipo
            raise InvalidMoneyError(
                f"O montante tem de ser Decimal, não {type(self.amount).__name__}."
            )
        if not self.amount.is_finite():
            raise InvalidMoneyError(f"Montante não finito: {self.amount}.")
        if self.amount < 0:
            raise InvalidMoneyError(
                f"Montante negativo: {self.amount}. Um preço praticado não é negativo."
            )

        exponent = self.amount.as_tuple().exponent
        if not isinstance(exponent, int):  # pragma: no cover - já coberto por is_finite
            raise InvalidMoneyError(f"Montante não finito: {self.amount}.")
        if -exponent > self.currency.minor_units:
            raise InvalidMoneyError(
                f"{self.amount} tem mais casas decimais do que {self.currency} admite "
                f"({self.currency.minor_units}). Usa Money.rounded() para arredondar de "
                f"forma explícita."
            )
        object.__setattr__(
            self, "amount", self.amount.quantize(Decimal(1).scaleb(-self.currency.minor_units))
        )

    # -- construção --------------------------------------------------------

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: Currency = EUR) -> "Money":
        """Constrói a partir de um valor exato, sem arredondar.

        Aceita ``str`` no formato neutro (ponto decimal), que é o formato em que os
        preços chegam do JSON-LD. Um valor com mais casas do que a moeda admite é
        recusado em vez de arredondado em silêncio.
        """
        try:
            decimal_amount = Decimal(amount) if not isinstance(amount, Decimal) else amount
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise InvalidMoneyError(f"Montante ilegível: {amount!r}.") from exc
        return cls(amount=decimal_amount, currency=currency)

    @classmethod
    def rounded(
        cls,
        amount: Decimal | int | str,
        currency: Currency = EUR,
        rounding: str = ROUND_HALF_UP,
    ) -> "Money":
        """Constrói arredondando à unidade menor da moeda, com o modo explícito.

        Existe para os poucos sítios onde arredondar é a operação correta. Fora desses,
        usa :meth:`of` e deixa o valor demasiado preciso falhar.
        """
        try:
            decimal_amount = Decimal(amount) if not isinstance(amount, Decimal) else amount
            quantized = decimal_amount.quantize(
                Decimal(1).scaleb(-currency.minor_units), rounding=rounding
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise InvalidMoneyError(f"Montante ilegível: {amount!r}.") from exc
        return cls(amount=quantized, currency=currency)

    @classmethod
    def from_pt_string(cls, text: str, currency: Currency = EUR) -> "Money":
        """Lê um preço escrito no formato português.

        Suporta vírgula decimal, ponto e espaço (incluindo não separável) como
        separador de milhares, e o símbolo antes ou depois do número.

        Recusa deliberadamente o formato neutro ``"59.00"``: em português o ponto é
        separador de milhares, e adivinhar qual dos dois significados se aplica trocaria
        um erro ruidoso por um preço errado no histórico. Para valores já normalizados
        — os que vêm do JSON-LD — usa :meth:`of`.
        """
        stripped = text.strip()
        if not stripped:
            raise InvalidMoneyError("Texto de preço vazio.")

        body, detected = _split_currency_symbol(stripped)
        if detected is not None and detected != currency:
            raise CurrencyMismatchError(
                f"O texto indica {detected}, mas foi pedida a leitura em {currency}."
            )

        body = body.translate({ord(character): None for character in _SPACE_CHARACTERS})
        if not body:
            raise InvalidMoneyError(f"Sem dígitos em {text!r}.")
        if body.startswith(("-", "+")):
            raise InvalidMoneyError(f"Preço com sinal não é aceite: {text!r}.")

        integer_part, decimal_part = _split_decimal_comma(body, text)
        integer_digits = _validate_integer_part(integer_part, text)

        if decimal_part is None:
            return cls(amount=Decimal(integer_digits), currency=currency)

        if not _DECIMALS.fullmatch(decimal_part):
            raise InvalidMoneyError(f"Parte decimal inválida em {text!r}.")
        if len(decimal_part) > currency.minor_units:
            raise InvalidMoneyError(
                f"{text!r} tem {len(decimal_part)} casas decimais e {currency} admite "
                f"{currency.minor_units}."
            )
        return cls(amount=Decimal(f"{integer_digits}.{decimal_part}"), currency=currency)

    # -- comparação --------------------------------------------------------

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Não se comparam nem combinam {self.currency} e {other.currency}."
            )

    def __lt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount >= other.amount

    # -- aritmética --------------------------------------------------------

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    # -- apresentação ------------------------------------------------------

    def format_pt(self) -> str:
        """Devolve o montante no formato português, com o símbolo depois do número.

        Usa espaço não separável antes do símbolo, que é a convenção tipográfica
        portuguesa e evita que o símbolo caia sozinho para a linha seguinte.
        """
        digits, _, decimals = f"{self.amount:f}".partition(".")
        grouped = f"{int(digits):,}".replace(",", ".")
        symbol = "€" if self.currency == EUR else self.currency.code
        if not decimals:
            return f"{grouped}\u00a0{symbol}"
        return f"{grouped},{decimals}\u00a0{symbol}"

    def __str__(self) -> str:
        return self.format_pt()


def _split_currency_symbol(text: str) -> tuple[str, Currency | None]:
    """Separa o símbolo de moeda do número, aceitando-o antes ou depois."""
    for symbol, currency in _CURRENCY_SYMBOLS.items():
        if text.upper().endswith(symbol):
            return text[: -len(symbol)], currency
        if text.upper().startswith(symbol):
            return text[len(symbol) :], currency
    return text, None


def _split_decimal_comma(body: str, original: str) -> tuple[str, str | None]:
    """Divide em parte inteira e decimal pela vírgula, exigindo no máximo uma."""
    if "," not in body:
        return body, None
    if body.count(",") > 1:
        raise InvalidMoneyError(f"Mais do que uma vírgula decimal em {original!r}.")
    integer_part, _, decimal_part = body.partition(",")
    return integer_part, decimal_part


def _validate_integer_part(integer_part: str, original: str) -> str:
    """Valida o agrupamento de milhares e devolve só os dígitos.

    Exige que os pontos agrupem de três em três. ``"59.00"`` falha aqui — e é para
    falhar: no formato português esse texto não representa cinquenta e nove.
    """
    if not integer_part:
        raise InvalidMoneyError(f"Sem parte inteira em {original!r}.")
    if "." in integer_part:
        if not _INTEGER_GROUPED.fullmatch(integer_part):
            raise InvalidMoneyError(
                f"Separador de milhares mal agrupado em {original!r}. No formato "
                f"português o ponto agrupa de três em três dígitos."
            )
        return integer_part.replace(".", "")
    if not _INTEGER_PLAIN.fullmatch(integer_part):
        raise InvalidMoneyError(f"Parte inteira inválida em {original!r}.")
    return integer_part
