# Everything a developer runs. `make help` lists it.
.DEFAULT_GOAL := help
BACKEND := cd backend &&
PG_TEST := postgresql+asyncpg://cappy:cappy@localhost:5433/postgres

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

up: ## Build and start the whole stack, then load the demo world
	mkdir -p .local
	docker compose up -d --build --wait
	cp .local/web.env web/.env.development.local
	$(MAKE) seed-demo
	@echo "API: http://localhost:8000/api   web: cd web && npm run dev   demo: host@demo.cappy.local / buyer@demo.cappy.local, Demo-pass-123!"

down: ## Stop the stack (keeps data)
	docker compose down

clean: ## Stop the stack and delete its data
	docker compose down -v
	rm -f .local/*.env

logs: ## Follow the services' logs
	docker compose logs -f catalog matching booking payments notifications gateway

seed-demo: ## Load the demo world (additive; local and staging only)
	docker compose exec -T catalog sh -c '. /run/cappy/local.env && python -m catalog.cli seed-demo --owner-map "$$DEMO_OWNER_MAP"'
	$(BACKEND) uv run python ../local/demo_profiles.py
	@# With real Stripe (test keys), give every demo owner a verified test account so they can be booked and paid.
	@if docker compose exec -T payments sh -c 'test "$$PAYMENTS_PROVIDER" = stripe'; then \
	  owners=$$(docker compose exec -T postgres psql -U cappy -d catalog -Atc "SELECT id FROM owners" | tr '\n' ' '); \
	  docker compose exec -T payments python -m payments.cli demo-payouts $$owners | tail -3; \
	fi

codes: ## Show sign-up confirmation codes cognito-local "emailed"
	docker compose logs cognito | grep -A1 'Code:' | tail -20

test: ## Unit and API tests (no Docker needed)
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run pytest -q

test-pg: ## Also the Postgres tests (needs `make up` for the database)
	$(BACKEND) CAPPY_TEST_PG=$(PG_TEST) uv run pytest -q

test-stripe: ## The Stripe contract test against stripe-mock
	docker run -d --rm --name cappy-stripe-mock -p 127.0.0.1:12111:12111 stripe/stripe-mock >/dev/null
	$(BACKEND) CAPPY_TEST_STRIPE_MOCK=http://localhost:12111 uv run pytest -q -m stripe_mock; s=$$?; docker stop cappy-stripe-mock >/dev/null; exit $$s

e2e: ## The whole journey against the running stack
	$(BACKEND) uv run python ../local/e2e.py

web: ## Type-check and build the web app
	cd web && npm ci && npm run build

.PHONY: help up down clean logs seed-demo codes test test-pg test-stripe e2e web

infra-validate: ## terraform fmt/validate every root
	cd infra && terraform fmt -check -recursive . && for d in bootstrap envs/staging envs/prod localstack; do (cd $$d && terraform init -backend=false -input=false >/dev/null && terraform validate) || exit 1; done

infra-local: ## Apply the event fabric to LocalStack and prove its routing (needs `make up`)
	cd infra/localstack && terraform init -input=false >/dev/null && terraform apply -auto-approve -input=false && uv run --project ../../backend python check.py

.PHONY: infra-validate infra-local

openapi: ## Regenerate docs/api/*.json from the services' code
	$(BACKEND) uv run python openapi.py

.PHONY: openapi

load: ## Sustained concurrent use of the running stack: no errors, no double booking
	$(BACKEND) uv run python ../local/load.py 50 60

.PHONY: load

load-spike: ## 10x the arrival rate for 60 s: shedding may answer 503, nothing else fails
	$(BACKEND) uv run python ../local/load.py spike 30 60

load-mixed: ## Open-model mixed journeys (90% browse, 8% signed-in, contested bookings)
	$(BACKEND) uv run python ../local/load.py mixed 40 120

load-soak: ## An hour at a steady rate: connections, memory and queue ages must stay flat
	$(BACKEND) uv run python ../local/load.py soak 20 3600

.PHONY: load-spike load-mixed load-soak
