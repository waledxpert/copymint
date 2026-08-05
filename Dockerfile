# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.11.6 AS uv

FROM python:3.13.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system --gid 10001 copymint \
    && useradd --system --uid 10001 --gid copymint --create-home copymint

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=copymint:copymint . .
RUN uv sync --frozen --no-dev

USER 10001:10001
EXPOSE 10000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "10000", "--proxy-headers"]
