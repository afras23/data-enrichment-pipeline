.PHONY: help lint format typecheck test migrate docker evaluate

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

lint: ## ruff check
	ruff check app/ tests/ eval/

format: ## ruff format
	ruff format app/ tests/ eval/

typecheck: ## mypy
	mypy app/ eval/ --ignore-missing-imports

test: ## pytest with coverage
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing --cov-fail-under=80

evaluate: ## offline evaluation report (mocked HTTP/AI; see eval/README.md)
	python -m eval.run_evaluation

migrate: ## alembic upgrade
	alembic upgrade head
