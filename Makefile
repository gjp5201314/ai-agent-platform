.PHONY: help dev build up down logs ps migrate seed clean \
        prod-build prod-push prod-pull prod-deploy prod-update prod-status prod-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Local Development
# ============================================================

dev: ## Install deps and run dev servers (requires Python venv + Node)
	cd frontend && npm install
	cd backend && pip install -r requirements.txt
	@echo "Starting backend..."
	cd backend && uvicorn app.main:app --reload --port 8000 &
	@echo "Starting frontend..."
	cd frontend && npm run dev

build: ## Build Docker images (local dev)
	docker compose build

up: ## Start all services (detached, local dev)
	docker compose up -d

down: ## Stop all services (local dev)
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

ps: ## Show running containers
	docker compose ps

clean: ## Stop and remove containers + volumes (DESTRUCTIVE)
	docker compose down -v

seed: ## Seed default agent config (requires running backend)
	curl -s http://localhost:8000/health | python -m json.tool

# ============================================================
# Production (ACR + Docker Swarm 滚动更新)
# ============================================================

prod-build: ## Build images locally for testing (uses docker compose build)
	docker compose -f docker-compose.prod.yml config 2>/dev/null; \
	docker compose build backend frontend

prod-push: ## Build + push images to ACR
	docker compose build backend frontend --no-cache
	docker tag ai-agent-platform-backend $(ACR_REGISTRY)/backend:latest
	docker tag ai-agent-platform-frontend $(ACR_REGISTRY)/frontend:latest
	docker push $(ACR_REGISTRY)/backend:latest
	docker push $(ACR_REGISTRY)/frontend:latest

prod-pull: ## Pull latest images from ACR (run on server)
	docker pull $(ACR_REGISTRY)/backend:latest
	docker pull $(ACR_REGISTRY)/frontend:latest

prod-deploy: ## First-time swarm deploy (run on server)
	bash scripts/swarm-init.sh

prod-update: ## Rolling update to latest (run on server, zero downtime)
	bash scripts/swarm-update.sh

prod-status: ## Show swarm service status
	@docker service ls --filter "name=$(STACK_NAME:-ai-agent)"
	@echo ""
	@docker service ps --no-trunc $(STACK_NAME:-ai-agent)_backend 2>/dev/null || true

prod-down: ## Remove swarm stack
	docker stack rm $(STACK_NAME:-ai-agent)
