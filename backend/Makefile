# Everyday commands. `uv` does the Python; compose does the stack.

.PHONY: sync test lint up down logs seed dev-catalog dev-matching dev-booking dev-gateway

sync:            ## install every service and the dev tools into .venv
	uv sync --all-packages

test: sync       ## run every service's tests
	uv run pytest -q

lint:
	uv run ruff check .

up:              ## build and start the whole stack (gateway on :8000)
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

seed:            ## regenerate the demo world from the frontend's seed.ts
	node scripts/export-seed.mjs ../cappy/cappy > libs/cappy_common/cappy_common/fixtures/seed.json

# Run one service on its own without Docker (sqlite + in-memory events).
dev-catalog:
	uv run --package cappy-catalog uvicorn catalog.main:app --port 8001 --reload
dev-matching:
	uv run --package cappy-matching uvicorn matching.main:app --port 8002 --reload
dev-booking:
	uv run --package cappy-booking uvicorn booking.main:app --port 8003 --reload
dev-gateway:
	uv run --package cappy-gateway uvicorn gateway.main:app --port 8000 --reload
