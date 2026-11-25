# syntax=docker/dockerfile:1

FROM python:3.14.10-slim-trixie AS python-base

FROM python-base AS dependencias
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY .python-version pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --group orientacao --no-install-project

FROM python-base AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=dependencias /app/.venv /app/.venv
COPY servicos/*.py ./servicos/
COPY servicos/orientacao/ ./servicos/orientacao/
COPY docs/parte-4/base-conhecimento/ ./docs/parte-4/base-conhecimento/

USER 10001:10001
CMD ["python", "-m", "servicos.orientacao.ingestao"]
