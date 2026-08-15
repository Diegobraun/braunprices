"""Configuração do registo estruturado.

Em produção o formato é JSON, porque a pergunta que se faz aos registos desta passagem
é agregada — "quantas falhas de que tipo, em que loja" — e isso responde-se com uma
consulta, não a ler linhas. Localmente o formato é legível, porque aí a pergunta é
outra.
"""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", output_format: str = "json") -> None:
    """Prepara o structlog para o resto do processo."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if output_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
