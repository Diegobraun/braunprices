.DEFAULT_GOAL := help
SHELL := /bin/bash

UV := $(shell command -v uv 2>/dev/null)
ARGS ?= --help

.PHONY: help setup unhide-pth lint format typecheck arch test test-unit test-integration run serve openapi clean

help: ## Mostra os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

guard-uv:
ifndef UV
	$(error uv nao encontrado. Instala com: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif

setup: guard-uv ## Cria o ambiente e instala tudo (runtime + dev + hooks)
	uv sync --all-groups
	$(MAKE) --no-print-directory unhide-pth
	uv run pre-commit install

unhide-pth: ## Limpa a flag UF_HIDDEN dos .pth do venv (só macOS)
# Em macOS, um .pth com a flag UF_HIDDEN é ignorado por site.addpackage() sem
# qualquer aviso, e o editable install fica inerte: `import braunprices` falha
# com o pacote aparentemente instalado. Repor a flag é idempotente e barato.
ifeq ($(shell uname), Darwin)
	@if [ -d .venv/lib ]; then \
		find .venv/lib -name '*.pth' -exec chflags nohidden {} + 2>/dev/null || true; \
	fi
endif

lint: guard-uv unhide-pth ## ruff (regras + formatação) e contratos de arquitetura
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

format: guard-uv unhide-pth ## Aplica a formatação e os fixes automáticos
	uv run ruff check --fix .
	uv run ruff format .

typecheck: guard-uv unhide-pth ## mypy --strict
	uv run mypy

arch: guard-uv unhide-pth ## Só os contratos de dependência entre camadas
	uv run lint-imports

test: guard-uv unhide-pth ## Toda a suite
	uv run pytest

test-unit: guard-uv unhide-pth ## Só o domínio puro (sem I/O, sem Docker)
	uv run pytest -m unit

test-integration: guard-uv unhide-pth ## Integração com Postgres real (requer Docker a correr)
	uv run pytest -m integration

run: guard-uv unhide-pth ## Executa a CLI de operação (make run ARGS="version")
	uv run braunprices $(ARGS)

serve: guard-uv unhide-pth ## Levanta a API pública em http://127.0.0.1:8000/docs
	uv run braunprices servir --recarregar

openapi: guard-uv unhide-pth ## Escreve o contrato OpenAPI em openapi.json
	@uv run python -c "import json, sys; from braunprices.interfaces.api.app import create_app; \
		json.dump(create_app().openapi(), sys.stdout, ensure_ascii=False, indent=2)" > openapi.json
	@echo "openapi.json escrito."

clean: ## Remove artefactos de build e caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache .import_linter_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
