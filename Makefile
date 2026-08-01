.PHONY: help install lint typecheck test record status validate telemetry types research desktop clean

help: ## List available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Sync Python environment (uv) and install pre-commit hooks
	uv sync --group dev
	uv run pre-commit install

lint: ## Ruff format check + lint
	uv run ruff format --check .
	uv run ruff check .

typecheck: ## Mypy over data/, ops/, tests/
	uv run mypy

test: ## Run the pytest suite
	uv run pytest

record: ## Start the market data recorder (Kraken + Coinbase public feeds)
	uv run python -m data.recorder

status: ## Process liveness, heartbeat age per venue, today's partition sizes, free disk
	uv run python -m ops.status

validate: ## Reconstruct books from raw data, score quality, append results to report.md
	uv run python -m data.validate

telemetry: ## Start the venue latency probe (runs alongside the recorder)
	uv run python -m ops.telemetry

types: ## Regenerate performance-report JSON Schema + desktop TS types (generated files are never edited by hand)
	uv run python -m backtest.reporting

research: ## Run the Phase B pipeline on a date: make research DATE=2026-07-31
	uv run python -m research --date $(DATE)

desktop: ## Run the desktop app in dev mode (requires Rust + Node, see desktop/README.md)
	cd desktop && npm run tauri dev

clean: ## Remove caches and build artifacts (never touches data/raw)
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './desktop/node_modules/*' -exec rm -rf {} +
	rm -rf desktop/dist desktop/src-tauri/target
