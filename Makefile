.PHONY: help setup api ui test lint fmt check evals docker-up docker-down clean clean-force audit

help: ## Show this help message
	@echo "\033[1;34m==================================================\033[0m"
	@echo "\033[1;34m MediCare: Multi-Agent AI Service Platform\033[0m"
	@echo "\033[1;34m==================================================\033[0m"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Initialize database schema, import seed CSVs, and index policies into var/
	uv run medicare-setup --all

api: ## Start FastAPI gateway server on port 8080
	uv run uvicorn medicare.api.app:create_app --factory --host 0.0.0.0 --port 8080

ui: ## Start Streamlit user interface on port 8501
	uv run streamlit run ui/app.py --server.port 8501

test: ## Run full test suite with pytest
	uv run pytest -q

lint: ## Run code linter with ruff
	uv run ruff check .

fmt: ## Format code with ruff
	uv run ruff format .

check: lint test audit ## Run linter, test suite, and hardcoding audit in sequence

evals: ## Run golden question benchmark evaluation
	uv run medicare-evals --out evals/report.md

docker-up: ## Start all services using Docker Compose
	docker compose up --build

docker-down: ## Stop Docker Compose services
	docker compose down

audit: ## Run hardcoded data and schema scanner
	uv run python scripts/audit_hardcoding.py

clean: ## Interactive cleanup of runtime databases, vector stores, and caches
	@read -p "Are you sure you want to delete caches and runtime state in var/? [y/N] " ans && if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
		$(MAKE) clean-force; \
	else \
		echo "Clean cancelled."; \
	fi

clean-force: ## Non-interactive force cleanup of var/ runtime state and caches
	rm -rf var/hospitals.db var/manifest.db var/chroma var/uploads var/langgraph_checkpoints.db var/platform.db
	rm -rf .pytest_cache .ruff_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Cleaned runtime state and caches."
