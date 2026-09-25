# One image recipe for every service. Build from backend/:
#   docker build --build-arg SERVICE=catalog -t cappy-catalog .
# Run the service:   (default CMD)
# Run migrations:    python -m cappy_common.migrations catalog
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ARG SERVICE
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version ./
COPY libs ./libs
COPY services ./services
RUN uv sync --frozen --no-dev --no-editable --package cappy-${SERVICE}

FROM python:3.12-slim-bookworm
ARG SERVICE
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 SERVICE=${SERVICE} PORT=8000 APP_ENV=prod LOG_JSON=true
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build --chown=app:app /app/.venv /app/.venv
USER app
EXPOSE 8000
# The venv's python is at the same path in both stages, so the copied entry points work.
CMD ["sh", "-c", "exec uvicorn --factory ${SERVICE}.main:create --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 20 --timeout-keep-alive 65 --no-server-header"]
