# syntax=docker/dockerfile:1

FROM python:3.14.10-slim-trixie AS python-base

FROM python-base AS dependencias
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY .python-version pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM python-base AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=dependencias /app/.venv /app/.venv
COPY servicos/*.py ./servicos/
COPY servicos/reservas/ ./servicos/reservas/

USER 10001:10001
EXPOSE 8004
CMD ["python", "-m", "uvicorn", "servicos.reservas.main:app", "--host", "0.0.0.0", "--port", "8004"]
