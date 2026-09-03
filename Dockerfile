FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN addgroup --system dutai && adduser --system --ingroup dutai dutai

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY app ./app
COPY cordis ./cordis

FROM base AS development
COPY tests ./tests
RUN python -m pip install --upgrade pip && python -m pip install ".[server,dev]"
RUN mkdir -p /data/sessions && chown -R dutai:dutai /data /app
USER dutai
CMD ["uvicorn", "app.server.controller:create_app", "--factory", "--reload", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS production
RUN python -m pip install --upgrade pip && python -m pip install ".[server]"
RUN mkdir -p /data/sessions && chown -R dutai:dutai /data /app
USER dutai

EXPOSE 8000
CMD ["uvicorn", "app.server.controller:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
