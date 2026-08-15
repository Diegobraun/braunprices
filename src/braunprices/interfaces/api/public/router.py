"""A superfície pública de leitura.

Anónima e só de leitura. Não há aqui nenhum caminho de escrita — nem sequer um
desligado por configuração — porque a superfície de escrita é outra, com outro prefixo
e outra autenticação. Duas superfícies separadas é o que impede que um engano de
encaminhamento transforme uma consulta numa alteração.

Os cabeçalhos de cache não são um detalhe de desempenho: o histórico de ontem já não
muda, e reafirmá-lo a cada pedido é gastar a base de dados a responder a perguntas cuja
resposta já foi dada.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from email.utils import format_datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from braunprices.application.queries.price_history import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from braunprices.domain.errors import DomainError
from braunprices.domain.model.price_observation import PriceObservation
from braunprices.domain.model.price_window import DEFAULT_WINDOW_DAYS
from braunprices.domain.value_objects.ean import EAN
from braunprices.domain.value_objects.observation_cursor import ObservationCursor
from braunprices.domain.value_objects.observed_at import ObservedAt
from braunprices.interfaces.api.dependencies import (
    PriceHistoryDep,
    ProductDep,
    ReferencePriceDep,
    StoresDep,
)
from braunprices.interfaces.api.public import cursors
from braunprices.interfaces.api.public.schemas import (
    HistoryOut,
    ProblemOut,
    ProductOut,
    ReferencePriceOut,
    StoreOut,
)

# Quanto tempo uma resposta pode ser reutilizada. A recolha é diária: uma resposta com
# minutos de idade descreve o mesmo que descreveria agora.
CACHE_SECONDS = 300

# Teto da janela pedida. Um ano é muito mais do que a lei exige e já é generoso para
# quem queira contexto; acima disso é um pedido de despejo com outro nome.
MAX_WINDOW_DAYS = 365

router = APIRouter(
    prefix="/api/v1",
    tags=["leitura"],
    responses={status.HTTP_404_NOT_FOUND: {"model": ProblemOut}},
)


@router.get("/lojas", summary="Lojas de que se recolhe")
def list_stores(stores: StoresDep, response: Response) -> list[StoreOut]:
    """Lista as lojas registadas e o ritmo declarado com que são visitadas."""
    _allow_caching(response)
    return [StoreOut.of(store) for store in stores()]


@router.get("/produtos/{product_id}", summary="Um produto e as suas referências")
def get_product(product_id: UUID, products: ProductDep, response: Response) -> ProductOut:
    """Devolve o produto e a última observação de cada referência."""
    view = products.by_id(product_id)
    if view is None:
        raise _not_found(f"Não há produto com o identificador {product_id}.")
    _allow_caching(response)
    return ProductOut.of(view)


@router.get(
    "/produtos",
    summary="Procurar produto por EAN",
    responses={status.HTTP_400_BAD_REQUEST: {"model": ProblemOut}},
)
def get_product_by_ean(
    products: ProductDep,
    response: Response,
    ean: Annotated[str, Query(description="Código de barras: EAN-8, EAN-13 ou UPC-A.")],
) -> ProductOut:
    """Devolve o produto com este EAN, que é a chave de casamento entre lojas."""
    view = products.by_ean(_parse_ean(ean))
    if view is None:
        raise _not_found(f"Não há produto observado com o EAN {ean}.")
    _allow_caching(response)
    return ProductOut.of(view)


@router.get(
    "/referencias/{listing_id}/historico",
    summary="Histórico observado de uma referência",
    responses={status.HTTP_400_BAD_REQUEST: {"model": ProblemOut}},
)
def get_history(  # noqa: PLR0913, PLR0917 - cada argumento é um parâmetro do pedido
    listing_id: UUID,
    history: PriceHistoryDep,
    response: Response,
    desde: Annotated[date | None, Query(description="Primeiro dia de Lisboa, inclusive.")] = None,
    ate: Annotated[date | None, Query(description="Último dia de Lisboa, inclusive.")] = None,
    limite: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None, Query(description="Valor de `cursor_seguinte` da página anterior.")
    ] = None,
) -> HistoryOut:
    """Devolve uma página do histórico, do facto mais antigo para o mais recente.

    Cada observação traz o dia, o preço, a disponibilidade e o URL de onde foi lida.
    Não há interpolação: dias sem observação continuam sem observação.
    """
    if desde is not None and ate is not None and desde > ate:
        raise _bad_request(
            f"O intervalo pedido está invertido: desde={desde} é posterior a ate={ate}."
        )

    page = history(listing_id, since=desde, until=ate, after=_parse_cursor(cursor), limit=limite)
    if page is None:
        raise _not_found(f"Não há referência de loja com o identificador {listing_id}.")

    _allow_caching(response)
    _stamp_last_modified(response, page.observations)
    next_cursor = cursors.encode(page.next_cursor) if page.next_cursor is not None else None
    return HistoryOut.of(page, next_cursor)


@router.get(
    "/referencias/{listing_id}/preco-de-referencia",
    summary="Preço de referência na data indicada",
    responses={status.HTTP_400_BAD_REQUEST: {"model": ProblemOut}},
)
def get_reference_price(
    listing_id: UUID,
    reference: ReferencePriceDep,
    response: Response,
    data: Annotated[
        date | None,
        Query(description="Data da aplicação do desconto. Por omissão, hoje em Lisboa."),
    ] = None,
    dias: Annotated[
        int, Query(ge=1, le=MAX_WINDOW_DAYS, description="Dias da janela.")
    ] = DEFAULT_WINDOW_DAYS,
) -> ReferencePriceOut:
    """Aplica a regra dos 30 dias ao histórico observado desta referência.

    A resposta descreve o que foi observado: o preço mais baixo praticado na janela, a
    regra que produziu o preço de referência, e quantas observações entraram na conta.
    Nada é afirmado sobre o que a loja anunciou — isso este sistema não observa.
    """
    answer = reference(listing_id, data or _today_in_lisbon(), dias)
    if answer is None:
        raise _not_found(f"Não há referência de loja com o identificador {listing_id}.")
    _allow_caching(response)
    if answer.latest is not None:
        _stamp_last_modified(response, [answer.latest])
    return ReferencePriceOut.of(answer)


def _parse_ean(value: str) -> EAN:
    try:
        return EAN(value)
    except DomainError as error:
        raise _bad_request(str(error)) from error


def _parse_cursor(value: str | None) -> ObservationCursor | None:
    if value is None:
        return None
    try:
        return cursors.decode(value)
    except cursors.InvalidCursorError as error:
        raise _bad_request(str(error)) from error


def _today_in_lisbon() -> date:
    return ObservedAt(datetime.now(UTC)).local_date


def _allow_caching(response: Response) -> None:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"


def _stamp_last_modified(response: Response, observations: Sequence[PriceObservation]) -> None:
    """Marca a resposta com o instante do facto mais recente que ela contém."""
    if not observations:
        return
    newest = max(observation.observed_at.instant for observation in observations)
    response.headers["Last-Modified"] = format_datetime(newest, usegmt=True)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
