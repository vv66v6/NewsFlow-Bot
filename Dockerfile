FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir ".[all]"


FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
# Do NOT copy src/ into /app at runtime. Bothost mounts /app and can mask
# the source tree; the installed package in /opt/venv must be authoritative.

# Install free local translation models. These are stored outside /app so
# Bothost's persistent /app mount does not hide them.
RUN /opt/venv/bin/argospm update \
    && /opt/venv/bin/argospm install translate-en_de \
    && /opt/venv/bin/argospm install translate-en_fr
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY LICENSE README.md ./

ENV PATH="/opt/venv/bin:$PATH"
# Intentionally no PYTHONPATH=/app/src: use the installed package from /opt/venv.
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DATABASE_URL=sqlite+aiosqlite:///./data/newsflow.db
ENV LOG_LEVEL=INFO
ENV API_ENABLED=false
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

RUN mkdir -p /app/data
RUN chmod 777 /app/data

EXPOSE 8000

CMD ["python", "-m", "newsflow.main"]
