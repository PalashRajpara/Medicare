# Running MediCare with Docker

This guide explains how to build and orchestrate MediCare using Docker and Docker Compose.

## Architecture

The Docker setup defines three services:
1. `medicare-init`: One-off initialization container that runs `medicare-setup --all`, initializing `var/hospitals.db`, `var/manifest.db`, and `var/chroma/`.
2. `medicare-api`: FastAPI application listening on port `8080`.
3. `medicare-ui`: Streamlit frontend listening on port `8501`.

## Storage & Volumes

- **Named Volume `medicare_var:/app/var`**: Persists runtime databases (`hospitals.db`, `platform.db`, `manifest.db`, `langgraph_checkpoints.db`) and vector indexes across container restarts.
- **Read-Only Bind Mounts**:
  - `./data/seed:/app/data/seed:ro`
  - `./data/policies:/app/data/policies:ro`

## Commands

```bash
# Start all services with automated build
docker compose up --build

# Run in background
docker compose up -d

# Check service logs
docker compose logs -f

# Stop services
docker compose down
```
