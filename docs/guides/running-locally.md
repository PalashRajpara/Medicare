# Running MediCare Locally

This guide walks you through running MediCare on your local development machine.

## Prerequisites

- **Python 3.11+**
- **uv** (recommended) or standard `pip`

## Quickstart via Makefile

```bash
# 1. Initialize environment and import seed data
make setup

# 2. Start the FastAPI backend service (port 8080)
make api

# 3. In another terminal, start the Streamlit UI (port 8501)
make ui
```

## Running Without Make

```bash
# Install dependencies
uv sync

# Run setup CLI to initialize database & index policies
uv run medicare-setup --all

# Start API server
uv run uvicorn medicare.api.app:create_app --factory --host 0.0.0.0 --port 8080

# Start UI
uv run streamlit run ui/app.py --server.port 8501
```

## Testing & Verification

```bash
# Run pytest test suite
make test

# Run code linter
make lint

# Run golden question evaluation benchmarks
make evals
```
