"""Configuração, lida do ambiente.

``pydantic`` vive aqui porque isto é uma borda do sistema: o sítio onde texto vindo de
fora se transforma em valores em que o resto do código pode confiar. Não entra no
domínio, e o contrato de ``import-linter`` verifica isso.

Nenhum segredo no repositório: o ``.env`` está no ``.gitignore`` e o ``.env.example``
mostra a forma sem mostrar valores.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from braunprices import __version__


class Settings(BaseSettings):
    """Definições de operação do BraunPrices."""

    model_config = SettingsConfigDict(
        env_prefix="BRAUNPRICES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://braunprices:braunprices@localhost:5432/braunprices",
        description="Ligação ao PostgreSQL.",
    )

    user_agent: str = Field(
        default=f"BraunPricesBot/{__version__} (+https://github.com/Diegobraun/braunprices)",
        description="Identificação nos pedidos. Identificável e com URL de contacto.",
    )
    contact_email: str = Field(default="", description="Contacto alternativo, opcional.")

    requests_per_second: float = Field(default=0.5, gt=0, le=5)
    max_concurrency_per_domain: int = Field(default=1, ge=1, le=4)
    request_timeout_seconds: float = Field(default=20.0, gt=0)

    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json", description="`json` para produção, `console` local.")
    timezone: str = Field(default="Europe/Lisbon")

    @field_validator("user_agent")
    @classmethod
    def must_identify_the_project_and_not_a_browser(cls, value: str) -> str:
        """Recusa um user-agent que se disfarce de browser.

        A regra existe no código de recolha, mas é aqui que ela pode ser contornada por
        configuração — e uma regra que se desliga com uma variável de ambiente não é uma
        regra. Ver ADR-0006.
        """
        forbidden = ("mozilla", "chrome", "safari", "edge", "gecko", "applewebkit")
        lowered = value.lower()
        if any(marker in lowered for marker in forbidden):
            message = (
                f"O user-agent {value!r} finge ser um browser. Este projeto identifica-se "
                f"sempre: usa algo como BraunPricesBot/<versão> (+<URL de contacto>)."
            )
            raise ValueError(message)
        if "http" not in lowered:
            message = (
                f"O user-agent {value!r} não tem URL de contacto. Quem receber os pedidos "
                f"tem de conseguir descobrir quem os está a fazer."
            )
            raise ValueError(message)
        return value


@lru_cache
def get_settings() -> Settings:
    """Devolve as definições, lidas uma vez por processo."""
    return Settings()
