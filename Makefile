.DEFAULT_GOAL := help
SHELL := /bin/bash

UV := $(shell command -v uv 2>/dev/null)
ARGS ?= --help

.PHONY: help setup lint format typecheck arch test test-unit test-integration run clean

help: ## Mostra os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

guard-uv:
ifndef UV
	$(error uv nao encontrado. Instala com: curl -LsSf https://astral.sh/uv/install.sh | sh)
endif

setup: guard-uv ## Cria o ambiente e instala tudo (runtime + dev + hooks)
	uv sync --all-groups
	uv run pre-commit install

lint: guard-uv ## ruff (regras + formatação) e contratos de arquitetura
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports

format: guard-uv ## Aplica a formatação e os fixes automáticos
	uv run ruff check --fix .
	uv run ruff format .

typecheck: guard-uv ## mypy --strict
	uv run mypy

arch: guard-uv ## Só os contratos de dependência entre camadas
	uv run lint-imports

test: guard-uv ## Toda a suite
	uv run pytest

test-unit: guard-uv ## Só o domínio puro (sem I/O, sem Docker)
	uv run pytest -m unit

test-integration: guard-uv ## Integração com Postgres real (requer Docker a correr)
	uv run pytest -m integration

run: guard-uv ## Executa a CLI de operação (make run ARGS="version")
	uv run braunprices $(ARGS)

clean: ## Remove artefactos de build e caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache .import_linter_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
