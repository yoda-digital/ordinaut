# Personal Agent Orchestrator - Docker Operations Makefile

.PHONY: help dev prod build clean logs status shell test stop restart

# Default target
help: ## Show this help message
	@echo "Personal Agent Orchestrator - Docker Operations"
	@echo "============================================="
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Development
dev: ## Start in development mode
	@./start.sh dev

dev-build: ## Start in development mode with rebuild
	@./start.sh dev --build

dev-logs: ## Start in development mode and follow logs
	@./start.sh dev --logs

dev-clean: ## Clean start in development mode
	@./start.sh dev --clean --build

# Production  
prod: ## Start in production mode
	@./start.sh prod

prod-build: ## Start in production mode with rebuild
	@./start.sh prod --build

prod-clean: ## Clean start in production mode  
	@./start.sh prod --clean --build

# Build operations
build: ## Build all Docker images
	@docker compose build

build-api: ## Build API service image
	@docker compose build api

build-scheduler: ## Build scheduler service image
	@docker compose build scheduler

build-worker: ## Build worker service image
	@docker compose build worker

# Service management
start: ## Start all services
	@docker compose up -d

stop: ## Stop all services
	@docker compose down

restart: ## Restart all services
	@docker compose restart

restart-api: ## Restart API service
	@docker compose restart api

restart-scheduler: ## Restart scheduler service
	@docker compose restart scheduler

restart-worker: ## Restart worker services
	@docker compose restart worker

# Scaling
scale-worker: ## Scale worker to 4 replicas
	@docker compose up -d --scale worker=4

scale-api: ## Scale API to 2 replicas  
	@docker compose up -d --scale api=2

# Logs and monitoring
logs: ## Follow logs from all services
	@docker compose logs -f

logs-api: ## Follow logs from API service
	@docker compose logs -f api

logs-scheduler: ## Follow logs from scheduler service
	@docker compose logs -f scheduler

logs-worker: ## Follow logs from worker services
	@docker compose logs -f worker

logs-db: ## Follow logs from database services
	@docker compose logs -f postgres redis

status: ## Show service status
	@docker compose ps
	@echo ""
	@echo "Resource Usage:"
	@docker stats --no-stream

health: ## Check service health
	@echo "Service Health Checks:"
	@docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
	@echo ""
	@echo "API Health:"
	@curl -s http://localhost:8080/health 2>/dev/null | jq . || echo "API not responding"

# Shell access
shell: ## Open shell in API container
	@docker compose exec api bash

shell-db: ## Open PostgreSQL shell
	@docker compose exec postgres psql -U orchestrator

shell-redis: ## Open Redis CLI
	@docker compose exec redis redis-cli

# Database operations  
db-backup: ## Backup database
	@mkdir -p backups
	@docker compose exec postgres pg_dump -U orchestrator orchestrator > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Database backed up to backups/"

db-restore: ## Restore database (specify FILE=backup.sql)
	@test -n "$(FILE)" || (echo "Usage: make db-restore FILE=backup.sql" && exit 1)
	@docker compose exec -i postgres psql -U orchestrator orchestrator < $(FILE)

db-reset: ## Reset database (WARNING: destroys all data)
	@echo "WARNING: This will destroy all data!"
	@read -p "Are you sure? (y/N) " -n 1 -r; echo; [[ $$REPLY =~ ^[Yy]$$ ]] || exit 1
	@docker compose down -v
	@docker volume rm -f ordinaut_pgdata ordinaut_redisdata 2>/dev/null || true
	@docker compose up -d

# Testing and validation
test: ## Run basic connectivity tests
	@echo "Testing service connectivity..."
	@docker compose exec postgres pg_isready -U orchestrator || echo "PostgreSQL not ready"
	@docker compose exec redis redis-cli ping || echo "Redis not responding"  
	@curl -f http://localhost:8080/health >/dev/null 2>&1 || echo "API not responding"
	@echo "Tests completed"

validate: ## Validate Docker Compose configuration
	@docker compose config --quiet && echo "✅ Docker Compose configuration is valid"

# Cleanup operations
clean: ## Clean up containers and images
	@docker compose down --remove-orphans
	@docker image prune -f

clean-all: ## Clean up everything including volumes (WARNING: destroys data)
	@echo "WARNING: This will destroy all data and images!"
	@read -p "Are you sure? (y/N) " -n 1 -r; echo; [[ $$REPLY =~ ^[Yy]$$ ]] || exit 1
	@docker compose down -v --remove-orphans
	@docker volume prune -f
	@docker image prune -af

# Development utilities
format-logs: ## Format logs with jq (requires jq)
	@docker compose logs --no-color | jq -r 'select(.time) | "\(.time) [\(.level)] \(.message)"' 2>/dev/null || docker compose logs

watch: ## Watch service status (requires watch command)
	@watch -n 5 'docker compose ps && echo "" && docker stats --no-stream'

# Environment setup
setup-dev: ## Setup development environment  
	@cp .env.example .env.dev
	@echo "Created .env.dev - edit with your development values"

setup-prod: ## Setup production environment
	@cp .env.example .env
	@echo "Created .env - IMPORTANT: edit with your production values!"

# Quick operations
quick-restart: stop start ## Quick restart all services

quick-logs: ## Show recent logs from all services
	@docker compose logs --tail=50

quick-status: ## Quick status check
	@docker compose ps --format "table {{.Name}}\t{{.Status}}"

# Advanced operations
network-info: ## Show network information
	@docker network inspect ordinaut-network 2>/dev/null | jq '.[0].Containers' || echo "Network not found"

volume-info: ## Show volume information  
	@docker volume ls | grep ordinaut

exec-api: ## Execute command in API container (CMD=command)
	@test -n "$(CMD)" || (echo "Usage: make exec-api CMD='command'" && exit 1)
	@docker compose exec api $(CMD)

exec-worker: ## Execute command in worker container (CMD=command)
	@test -n "$(CMD)" || (echo "Usage: make exec-worker CMD='command'" && exit 1)  
	@docker compose exec worker $(CMD)

# Security scans
security-scan: ## Basic security scan of images
	@echo "Scanning images for vulnerabilities..."
	@docker compose config --services | xargs -I {} sh -c 'echo "=== Scanning {} ===" && docker scout cves ordinaut-{} || echo "Scout not available"'