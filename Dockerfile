# syntax=docker/dockerfile:1

# --- Frontend: build the Vite bundle ---------------------------------------
FROM --platform=$BUILDPLATFORM node:24-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Backend dependencies: resolve the locked virtualenv -------------------
FROM python:3.13-slim AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# --- Dev tools: Python, uv, and Node for lint, tests, and codegen ----------
# Used only by compose.dev.yaml. Not part of the published image.
FROM node:24-slim AS tools
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_LINK_MODE=copy
RUN uv python install 3.13 && chmod -R a+rX /opt/uv-python
# Caches, the virtualenv, and HOME live outside the bind-mounted repo and work for any UID.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/cache/venv \
    UV_CACHE_DIR=/cache/uv \
    npm_config_cache=/cache/npm \
    npm_config_update_notifier=false \
    HOME=/tmp
RUN mkdir -p /cache && chmod 1777 /cache
WORKDIR /repo

# --- Runtime (default target) ---------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH
RUN useradd --system --uid 1000 --no-create-home runpad
WORKDIR /app
COPY --from=backend-deps /app/.venv ./.venv
COPY backend/alembic.ini backend/docker-entrypoint.sh ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=frontend /src/dist ./app/static
USER runpad
EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
