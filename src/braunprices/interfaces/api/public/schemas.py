"""As formas que a API pública devolve.

Duas regras moldam este ficheiro.

**Dinheiro é texto decimal, nunca número.** ``59.99`` em JSON é um `double` para quase
todos os leitores, e um cêntimo perdido num arredondamento é um facto errado publicado
sobre uma empresa identificada. O montante viaja como string, com a moeda ao lado.

**A linguagem é descritiva.** O sistema afirma que um preço foi observado num dia, com
o URL de onde foi lido. Não qualifica a conduta de ninguém — nem nos nomes dos campos,
nem nas descrições que aparecem no OpenAPI.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from braunprices.application.queries.catalogue import ObservedListing, ProductView
from braunprices.application.queries.price_history import HistoryPage
from braunprices.application.queries.reference_price import ReferencePriceAnswer
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.store import Store
from braunprices.domain.rules.price_reference import ReferenceBasis
from braunprices.domain.value_objects.money import Money


class MoneyOut(BaseModel):
    """Um montante, em texto decimal, com a moeda."""

    model_config = ConfigDict(frozen=True)

    montante: str = Field(description="Montante em texto decimal, por exemplo `59.99`.")
    moeda: str = Field(description="Código ISO 4217, por exemplo `EUR`.")

    @classmethod
    def of(cls, money: Money) -> "MoneyOut":
        """Cria a partir do valor de domínio."""
        return cls(montante=str(money.amount), moeda=money.currency.code)


class StoreOut(BaseModel):
    """Uma loja de que se recolhe."""

    model_config = ConfigDict(frozen=True)

    slug: str
    nome: str
    dominio: str
    pedidos_por_segundo: float = Field(
        description="Ritmo máximo a que esta loja é visitada, declarado publicamente."
    )

    @classmethod
    def of(cls, store: Store) -> "StoreOut":
        """Cria a partir da entidade de domínio."""
        return cls(
            slug=store.slug.value,
            nome=store.name,
            dominio=store.base_domain,
            pedidos_por_segundo=store.rate_limit.requests_per_second,
        )


class ObservationOut(BaseModel):
    """Um preço observado, com a proveniência que o torna verificável."""

    model_config = ConfigDict(frozen=True)

    observado_em: datetime = Field(description="Instante da observação, em UTC.")
    dia: date = Field(description="Dia de Lisboa a que a observação pertence.")
    preco: MoneyOut
    disponibilidade: str
    conta_como_preco_praticado: bool = Field(
        description=(
            "Indica se esta observação entra no cálculo da janela legal. Um preço "
            "mostrado em produto esgotado não é um preço a que alguém pudesse comprar."
        )
    )
    url: str = Field(description="Página de onde o preço foi lido.")
    impressao_do_conteudo: str = Field(
        description="Hash do conteúdo de onde o preço foi extraído, para verificação posterior."
    )

    @classmethod
    def of(cls, observation: PriceObservation) -> "ObservationOut":
        """Cria a partir da observação de domínio."""
        return cls(
            observado_em=observation.observed_at.instant,
            dia=observation.local_date,
            preco=MoneyOut.of(observation.price),
            disponibilidade=observation.availability.value,
            conta_como_preco_praticado=observation.counts_as_price_practised,
            url=observation.source_url,
            impressao_do_conteudo=observation.raw_hash,
        )


class ListingOut(BaseModel):
    """Uma referência de produto dentro de uma loja."""

    model_config = ConfigDict(frozen=True)

    listing_id: UUID
    loja: str
    referencia_na_loja: str
    url: str
    ativa: bool


class ObservedListingOut(ListingOut):
    """Uma referência com a última observação conhecida."""

    ultima_observacao: ObservationOut | None

    @classmethod
    def of(cls, observed: ObservedListing) -> "ObservedListingOut":
        """Cria a partir da vista de aplicação."""
        return cls(
            listing_id=observed.listing.listing_id,
            loja=observed.listing.store_slug.value,
            referencia_na_loja=observed.listing.external_id,
            url=observed.listing.url,
            ativa=observed.listing.is_active,
            ultima_observacao=(
                ObservationOut.of(observed.latest) if observed.latest is not None else None
            ),
        )


class ProductOut(BaseModel):
    """Um produto e as referências que o representam em cada loja."""

    model_config = ConfigDict(frozen=True)

    product_id: UUID
    nome: str
    ean: str | None
    referencias: list[ObservedListingOut]

    @classmethod
    def of(cls, view: ProductView) -> "ProductOut":
        """Cria a partir da vista de aplicação."""
        return cls(
            product_id=view.product.product_id,
            nome=view.product.canonical_name,
            ean=view.product.ean.value if view.product.ean is not None else None,
            referencias=[ObservedListingOut.of(observed) for observed in view.listings],
        )


class HistoryOut(BaseModel):
    """Uma página do histórico observado de uma referência."""

    model_config = ConfigDict(frozen=True)

    listing_id: UUID
    loja: str
    produto: str
    url: str
    observacoes: list[ObservationOut]
    cursor_seguinte: str | None = Field(
        description=(
            "Valor a passar em `cursor` para ler a página seguinte. Ausente quando não "
            "há mais histórico. A posição é o último facto lido, e não um deslocamento: "
            "num histórico a que se acrescentam factos, paginar por deslocamento "
            "devolveria repetições ou saltos."
        )
    )

    @classmethod
    def of(cls, page: HistoryPage, next_cursor: str | None) -> "HistoryOut":
        """Cria a partir da página de aplicação."""
        return cls(
            listing_id=page.listing.listing_id,
            loja=page.store.slug.value,
            produto=page.product.canonical_name,
            url=page.listing.url,
            observacoes=[ObservationOut.of(observation) for observation in page.observations],
            cursor_seguinte=next_cursor,
        )


class WindowOut(BaseModel):
    """A janela de dias sobre a qual a regra foi calculada."""

    model_config = ConfigDict(frozen=True)

    inicio: date = Field(description="Primeiro dia incluído.")
    fim_exclusivo: date = Field(description="Dia da aplicação do desconto, já fora da janela.")
    dias: int


class ReferencePriceOut(BaseModel):
    """A resposta à pergunta que dá razão de ser ao projeto.

    Descreve o que foi observado. Não afirma que alguma loja cumpriu ou deixou de
    cumprir seja o que for: para isso seria preciso saber o que a loja anunciou, e isso
    este sistema não observa.
    """

    model_config = ConfigDict(frozen=True)

    listing_id: UUID
    produto: str
    url: str
    janela: WindowOut
    preco_de_referencia: MoneyOut | None = Field(
        description=(
            "Preço que teria de ser indicado como anterior ao anunciar uma redução "
            "nesta data. Ausente quando não há observações elegíveis na janela."
        )
    )
    base_da_referencia: ReferenceBasis | None = Field(
        description=(
            "Regra que produziu o preço acima: `lowest_in_window` para a regra geral, "
            "`before_progressive_reduction` para o n.º 5 do artigo."
        )
    )
    mais_baixo_na_janela: MoneyOut | None
    observacoes_consideradas: int
    ultima_observacao: ObservationOut | None
    ha_historico_suficiente: bool = Field(
        description=(
            "Falso quando não há observação elegível na janela. Nesse caso não se "
            "responde zero nem se estima: não se sabe."
        )
    )

    @classmethod
    def of(cls, answer: ReferencePriceAnswer) -> "ReferencePriceOut":
        """Cria a partir da resposta de aplicação."""
        return cls(
            listing_id=answer.listing.listing_id,
            produto=answer.product.canonical_name,
            url=answer.listing.url,
            janela=WindowOut(
                inicio=answer.window.start,
                fim_exclusivo=answer.window.end_exclusive,
                dias=answer.window.window_days,
            ),
            preco_de_referencia=(
                MoneyOut.of(answer.reference.price) if answer.reference is not None else None
            ),
            base_da_referencia=(answer.reference.basis if answer.reference is not None else None),
            mais_baixo_na_janela=(
                MoneyOut.of(answer.lowest_in_window)
                if answer.lowest_in_window is not None
                else None
            ),
            observacoes_consideradas=answer.observations_considered,
            ultima_observacao=(
                ObservationOut.of(answer.latest) if answer.latest is not None else None
            ),
            ha_historico_suficiente=answer.has_enough_history,
        )


class ProblemOut(BaseModel):
    """O corpo de uma resposta de erro."""

    model_config = ConfigDict(frozen=True)

    detail: str


class HealthOut(BaseModel):
    """Estado do serviço."""

    model_config = ConfigDict(frozen=True)

    versao: str
    base_de_dados: bool = Field(description="Indica se a base de dados respondeu.")


__all__ = [
    "HealthOut",
    "HistoryOut",
    "ListingOut",
    "MoneyOut",
    "ObservationOut",
    "ObservedListingOut",
    "ProblemOut",
    "ProductOut",
    "ReferencePriceOut",
    "StoreOut",
    "WindowOut",
]
