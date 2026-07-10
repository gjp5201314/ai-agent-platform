.PHONY: help dev build up down logs ps migrate seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Install frontend deps and run dev servers (requires Python venv + Node)
	cd frontend && npm install
	cd backend && pip install -r requirements.txt
	@echo "Starting backend..."
	cd backend && uvicorn app.main:app --reload --port 8000 &
	@echo "Starting frontend..."
	cd frontend && npm run dev

build: ## Build Docker images
	docker compose build

up: ## Start all services (detached)
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

ps: ## Show running containers
	docker compose ps

clean: ## Stop and remove containers + volumes (DESTRUCTIVE)
	docker compose down -v
	docker system prune -f

seed: ## Seed default agent config (requires running backend)
	curl -s http://localhost:8000/health | python -m json.tool
