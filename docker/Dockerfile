# syntax=docker/dockerfile:1

# Single image shared by every app service (django, init/migrate,
# celery-beat, celery-worker) — they run identical code, only the
# command differs. Keeps dependencies and the Python/Django version in
# lockstep across all of them instead of building four separate images.

FROM python:3.14-alpine AS builder

RUN apk add --no-cache build-base postgresql-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY manage.py README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

FROM python:3.14-alpine AS runtime

RUN apk add --no-cache libpq && \
    addgroup -S ordy && adduser -S ordy -G ordy

WORKDIR /app

COPY --from=builder --chown=ordy:ordy /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=core.frameworks.django_app.config.settings

USER ordy
