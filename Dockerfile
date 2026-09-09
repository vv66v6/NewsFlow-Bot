# NewsFlow Bot - Bothost Dockerfile

# ============================================
# Builder
# ============================================

FROM python:3.11-slim AS builder

WORKDIR /app

# Build dependencies for lxml and other C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Create virtual environment
RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Install NewsFlow with all optional features:
# translation, OpenAI, DeepL, Google, API, Redis, etc.
RUN pip install --no-cache-dir ".[all]"

# ============================================
# Runtime
# ============================================

FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash newsflow

# Copy installed Python environment
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY --chown=newsflow:newsflow src/ ./src/
COPY --chown=newsflow:newsflow alembic/ ./alembic/
COPY --chown=newsflow:newsflow alembic.ini ./alembic.ini
COPY --chown=newsflow:newsflow LICENSE README.md ./

# NewsFlow configuration
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Persistent SQLite database
ENV DATABASE_URL=sqlite+aiosqlite:///./data/newsflow.db

ENV LOG_LEVEL=INFO
ENV API_ENABLED=false
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

# Persistent data directory
RUN mkdir -p /app/data && chown newsflow:newsflow /app/data

USER newsflow

EXPOSE 8000

# Start NewsFlow
CMD ["python", "-m", "newsflow.main"]
