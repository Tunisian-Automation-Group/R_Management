# Build from the backend root: docker build -f services/catalog/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock .python-version ./
COPY libs ./libs
COPY services ./services
RUN uv sync --frozen --no-dev --package cappy-catalog

EXPOSE 8001
CMD ["uv", "run", "--no-sync", "--package", "cappy-catalog", "uvicorn", "catalog.main:app", "--host", "0.0.0.0", "--port", "8001"]
