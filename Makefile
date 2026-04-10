.PHONY: help lint format typecheck test migrate docker

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

lint: ## ruff check
	ruff check app/ tests/

format: ## ruff format
	ruff format app/ tests/

typecheck: ## mypy
	mypy app/ --ignore-missing-imports

test: ## pytest with coverage
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing --cov-fail-under=80

migrate: ## alembic upgrade
	alembic upgrade head
