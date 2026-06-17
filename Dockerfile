ARG PYTHON_VERSION=3.12.11

FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

WORKDIR /app

#dep layer
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-editable

#app layer
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY openapi.yaml ./openapi.yaml
COPY openapi.json ./openapi.json
COPY tools/run_migrations.sh ./tools/run_migrations.sh

RUN chmod +x ./tools/run_migrations.sh

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/live').read()"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --proxy-headers --forwarded-allow-ips='*'"]



## FASTER

# ARG PYTHON_VERSION=3.12.11
# ARG UV_VERSION=0.11.6
# ARG APP_UID=10001
# ARG APP_GID=10001

# FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# FROM python:${PYTHON_VERSION}-slim AS base

# ARG APP_UID
# ARG APP_GID

# ENV PYTHONUNBUFFERED=1 \
#     PYTHONDONTWRITEBYTECODE=1 \
#     UV_LINK_MODE=copy \
#     UV_PYTHON_DOWNLOADS=0 \
#     PATH="/app/.venv/bin:$PATH"

# RUN groupadd --gid "${APP_GID}" appuser \
#     && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin appuser

# WORKDIR /app

# FROM base AS deps

# COPY pyproject.toml uv.lock ./

# RUN --mount=from=uv,source=/uv,target=/bin/uv \
#     --mount=type=cache,target=/root/.cache/uv \
#     uv sync --locked --no-install-project --no-dev --no-editable

# FROM deps AS runtime

# ARG APP_UID
# ARG APP_GID

# COPY --link --chown=${APP_UID}:${APP_GID} app ./app
# COPY --link --chown=${APP_UID}:${APP_GID} openapi.yaml ./openapi.yaml
# COPY --link --chown=${APP_UID}:${APP_GID} openapi.json ./openapi.json

# RUN --mount=from=uv,source=/uv,target=/bin/uv \
#     --mount=type=cache,target=/root/.cache/uv \
#     uv sync --locked --no-dev --no-editable

# USER appuser

# EXPOSE 8080

# HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
#     CMD python -c "import os, urllib.request; port=os.environ.get('PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/live').read()"

# CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --proxy-headers --forwarded-allow-ips='*'"]

