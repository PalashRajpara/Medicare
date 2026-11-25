# Stage 1: Build & Dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md .env.example ./
COPY config/ ./config/
COPY data/ ./data/
COPY medicare/ ./medicare/
COPY ui/ ./ui/
COPY .streamlit/ ./.streamlit/

RUN pip install --upgrade pip && \
    pip install --prefix=/install .

# Stage 2: Minimal Runtime
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.11/site-packages:$PYTHONPATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /install
COPY pyproject.toml README.md .env.example ./
COPY config/ ./config/
COPY data/ ./data/
COPY medicare/ ./medicare/
COPY ui/ ./ui/
COPY .streamlit/ ./.streamlit/

# Non-root user configuration for container security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/var && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8080 8501

CMD ["uvicorn", "medicare.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
