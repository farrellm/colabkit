.PHONY: help fmt check

SHELL := bash
.SHELLFLAGS := -euo pipefail -c

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-8s\033[0m %s\n", $$1, $$2}'

fmt: ## Format in place
	uv run ruff format .
	uv run ruff check --fix .

check: ## Format check, lint, types, tests
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest
