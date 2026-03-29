## the 54 sec build

ARG PYTHON_VERSION=3.12.11-slim

FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

WORKDIR /app

# deps layer
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# app layer
COPY app ./app
COPY openapi.yaml ./openapi.yaml
COPY openapi.json ./openapi.json

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live').read()"

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]

# FROM python:3.12-slim

# ENV PYTHONUNBUFFERED=1 \
#     UV_COMPILE_BYTECODE=1 \
#     UV_LINK_MODE=copy \
#     PATH="/app/.venv/bin:$PATH"

# WORKDIR /app

# # Install uv
# COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

# # Install only dependencies first
# COPY pyproject.toml uv.lock ./
# RUN uv sync --frozen --no-install-project --no-dev

# # Copy app source
# COPY app ./app
# COPY openapi.yaml ./openapi.yaml
# COPY openapi.json ./openapi.json
# COPY README.md ./README.md

# # Create non-root runtime user
# RUN useradd --create-home --shell /usr/sbin/nologin appuser \
#     && chown -R appuser:appuser /app

# USER appuser

# EXPOSE 8000

# # Replace /health with your real health endpoint
# HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
#     CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live').read()"

# CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
