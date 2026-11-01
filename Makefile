.PHONY: help migrate migrate-create migrate-up up down restart recreate logs flush build lint

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run Ruff linting
	uv run --extra dev ruff check .

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add users table")
	docker compose -f docker/docker-compose.yml run --rm api alembic revision --autogenerate -m "$(MSG)"

migrate-up: ## Apply all pending migrations
	docker compose -f docker/docker-compose.yml run --rm api alembic upgrade head

migrate-down: ## Rollback last migration
	docker compose -f docker/docker-compose.yml run --rm api alembic downgrade -1

migrate-history: ## Show migration history
	docker compose -f docker/docker-compose.yml run --rm api alembic history

up: ## Start the stack
	docker compose -f docker/docker-compose.yml up -d --force-recreate

build: ## Rebuild images and start the stack
	docker compose -f docker/docker-compose.yml up -d --build

down: ## Stop and remove the stack
	docker compose -f docker/docker-compose.yml down

down-v: ## Stop and remove the volumes
	docker compose -f docker/docker-compose.yml down -v

restart: ## Restart the stack
	docker compose -f docker/docker-compose.yml restart

logs: ## Tail logs
	docker compose -f docker/docker-compose.yml logs -f

ps: ## Show running containers
	docker compose -f docker/docker-compose.yml ps

include .env
export

flush: ## Drop all tables and recreate them using the checked-in migration history
	docker compose -f docker/docker-compose.yml exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	docker compose -f docker/docker-compose.yml run --rm api alembic upgrade head
