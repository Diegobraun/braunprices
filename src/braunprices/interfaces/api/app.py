"""A aplicação HTTP.

Duas superfícies vivem sob o mesmo processo, e **não** sob o mesmo router: a pública,
anónima e só de leitura, montada aqui; e a de administração, autenticada e com escrita,
que entra com o seu próprio prefixo e as suas próprias dependências quando existir.
Mantê-las separadas desde o primeiro dia é mais barato do que separá-las depois de a
primeira rota de escrita já ter nascido no sítio errado.

O container é montado uma vez, no arranque, e fechado no fim. Montá-lo por pedido
criaria um pool de ligações por pedido, que é a forma mais rápida de esgotar um
Postgres com tráfego nenhum.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from braunprices import __version__
from braunprices.infrastructure.composition import Container, build_container
from braunprices.infrastructure.config import Settings, get_settings
from braunprices.infrastructure.logging import configure_logging
from braunprices.interfaces.api.public.router import router as public_router
from braunprices.interfaces.api.public.schemas import HealthOut

logger = structlog.get_logger(__name__)

DESCRIPTION = """
Histórico de preços observados em lojas online portuguesas.

Cada preço aqui é um **facto observado**, com data, hora e o URL de onde foi lido. Uma
observação nunca é alterada nem apagada: se o preço muda, escreve-se outra observação.

A API descreve o que foi observado. Não qualifica a conduta de nenhuma loja — para isso
seria preciso saber o que a loja anunciou, e isso não é observado por este sistema.

O [Decreto-Lei n.º 109-G/2021](https://diariodarepublica.pt/dr/detalhe/decreto-lei/109-g-2021-176907406)
obriga quem anuncia uma redução de preço a indicar o preço mais baixo praticado nos 30
dias consecutivos anteriores. É esse número que o endpoint `preco-de-referencia`
calcula a partir do histórico observado.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Monta o container no arranque e larga as ligações no fim."""
    settings: Settings = app.state.settings
    configure_logging(level=settings.log_level, output_format=settings.log_format)
    container = build_container(settings)
    app.state.container = container
    logger.info("api.arrancada", versao=__version__)
    try:
        yield
    finally:
        container.close()
        logger.info("api.terminada")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Monta a aplicação pública."""
    app = FastAPI(
        title="BraunPrices",
        version=__version__,
        summary="Histórico de preços do retalho online português.",
        description=DESCRIPTION,
        license_info={"name": "AGPL-3.0-or-later", "identifier": "AGPL-3.0-or-later"},
        contact={
            "name": "BraunPrices",
            "url": "https://github.com/Diegobraun/braunprices",
        },
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.settings = settings if settings is not None else get_settings()

    # A superfície pública é de leitura anónima e os dados são para ser lidos por
    # terceiros — restringir a origem não protegeria nada que já não esteja público.
    # A superfície de administração terá a política oposta, e por isso vive noutro sítio.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(public_router)

    @app.get("/saude", tags=["operação"], summary="Estado do serviço")
    def health() -> HealthOut:
        """Diz se o processo está de pé e se a base de dados responde."""
        return HealthOut(versao=__version__, base_de_dados=_database_answers(app.state.container))

    return app


def _database_answers(container: Container) -> bool:
    """Faz a pergunta mais barata possível à base de dados."""
    if container.engine is None:  # pragma: no cover - só num container montado à mão
        return False
    try:
        with container.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # qualquer falha dá a mesma resposta: a base de dados não responde
        logger.warning("api.base_de_dados_sem_resposta", exc_info=True)
        return False
    return True


app = create_app()

__all__ = ["app", "create_app"]
