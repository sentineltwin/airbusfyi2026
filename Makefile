# ═══════════════════════════════════════════════════════════════
# SENTINELTWIN — Master Makefile
# Airworthiness Assurance Platform — Build & Deploy System
# ═══════════════════════════════════════════════════════════════

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Project metadata ──────────────────────────────────────────
PROJECT      := sentineltwin
VERSION      := 4.2.1
BUILD_DATE   := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT   := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
DOCKER_TAG   := $(VERSION)-$(GIT_COMMIT)

# ── Directories ───────────────────────────────────────────────
BACKEND_DIR  := ./backend
FRONTEND_DIR := ./frontend
INFRA_DIR    := ./infra
SCRIPTS_DIR  := ./scripts
REPORTS_DIR  := ./reports
LOGS_DIR     := ./logs
MODELS_DIR   := ./models

# ── Docker ────────────────────────────────────────────────────
COMPOSE      := docker compose
COMPOSE_FILE := docker-compose.yml
COMPOSE_PROD := docker-compose.prod.yml

# ── Python ────────────────────────────────────────────────────
PYTHON       := python3
PIP          := pip3
VENV         := .venv
VENV_BIN     := $(VENV)/bin

# ── Colors ────────────────────────────────────────────────────
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
CYAN   := \033[0;36m
WHITE  := \033[0;37m
RESET  := \033[0m
BOLD   := \033[1m

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "$(BOLD)$(CYAN)╔══════════════════════════════════════════════════════╗$(RESET)"
	@echo "$(BOLD)$(CYAN)║         SENTINELTWIN v$(VERSION) — Build System          ║$(RESET)"
	@echo "$(BOLD)$(CYAN)║    Airworthiness Assurance Platform Orchestrator     ║$(RESET)"
	@echo "$(BOLD)$(CYAN)╚══════════════════════════════════════════════════════╝$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ═══════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════

.PHONY: setup
setup: setup-dirs setup-python setup-frontend ## Full development environment setup
	@echo "$(GREEN)✓ SentinelTwin development environment ready$(RESET)"

.PHONY: setup-dirs
setup-dirs: ## Create required directories
	@echo "$(CYAN)Creating project directories...$(RESET)"
	@mkdir -p $(LOGS_DIR) $(REPORTS_DIR) $(MODELS_DIR)
	@mkdir -p $(BACKEND_DIR)/logs $(BACKEND_DIR)/reports
	@mkdir -p $(INFRA_DIR)/docker/postgres
	@mkdir -p $(INFRA_DIR)/docker/nginx
	@mkdir -p $(INFRA_DIR)/monitoring/grafana/{dashboards,datasources}
	@echo "$(GREEN)✓ Directories created$(RESET)"

.PHONY: setup-python
setup-python: ## Create Python virtual environment and install dependencies
	@echo "$(CYAN)Setting up Python environment...$(RESET)"
	@$(PYTHON) -m venv $(VENV)
	@$(VENV_BIN)/pip install --upgrade pip
	@$(VENV_BIN)/pip install -r $(BACKEND_DIR)/requirements.txt
	@echo "$(GREEN)✓ Python environment ready$(RESET)"

.PHONY: setup-frontend
setup-frontend: ## Install Node.js dependencies
	@echo "$(CYAN)Installing frontend dependencies...$(RESET)"
	@cd $(FRONTEND_DIR) && npm install
	@echo "$(GREEN)✓ Frontend dependencies installed$(RESET)"

.PHONY: env
env: ## Copy example env file
	@cp -n .env.example .env && echo "$(GREEN)✓ .env created$(RESET)" || echo "$(YELLOW).env already exists$(RESET)"

# ═══════════════════════════════════════════════════════════════
# DEVELOPMENT
# ═══════════════════════════════════════════════════════════════

.PHONY: dev
dev: ## Start full development stack (Docker infra + local backend + frontend)
	@echo "$(CYAN)Starting SentinelTwin development stack...$(RESET)"
	@$(MAKE) infra-up
	@sleep 5
	@$(MAKE) backend-dev &
	@$(MAKE) frontend-dev

.PHONY: backend-dev
backend-dev: ## Start backend in development mode (hot reload)
	@echo "$(CYAN)Starting FastAPI backend (dev mode)...$(RESET)"
	@cd $(BACKEND_DIR) && \
		$(VENV_BIN)/python -m uvicorn main:app \
		--host 0.0.0.0 \
		--port 8000 \
		--reload \
		--log-level info \
		--access-log

.PHONY: frontend-dev
frontend-dev: ## Start frontend dev server
	@echo "$(CYAN)Starting Vite dev server...$(RESET)"
	@cd $(FRONTEND_DIR) && npm run dev

.PHONY: infra-up
infra-up: ## Start infrastructure services (DB, Redis, Kafka) only
	@echo "$(CYAN)Starting infrastructure services...$(RESET)"
	@$(COMPOSE) up -d postgres redis kafka zookeeper
	@echo "$(CYAN)Waiting for services to be ready...$(RESET)"
	@sleep 10
	@echo "$(GREEN)✓ Infrastructure services running$(RESET)"

.PHONY: infra-down
infra-down: ## Stop infrastructure services
	@$(COMPOSE) stop postgres redis kafka zookeeper

# ═══════════════════════════════════════════════════════════════
# DOCKER
# ═══════════════════════════════════════════════════════════════

.PHONY: up
up: ## Start all services with Docker Compose
	@echo "$(CYAN)Starting SentinelTwin stack...$(RESET)"
	@$(COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo ""
	@echo "$(GREEN)$(BOLD)╔══════════════════════════════════════╗$(RESET)"
	@echo "$(GREEN)$(BOLD)║  SENTINELTWIN OPERATIONAL            ║$(RESET)"
	@echo "$(GREEN)$(BOLD)╠══════════════════════════════════════╣$(RESET)"
	@echo "$(GREEN)$(BOLD)║  Frontend:   http://localhost:3000   ║$(RESET)"
	@echo "$(GREEN)$(BOLD)║  API:        http://localhost:8000   ║$(RESET)"
	@echo "$(GREEN)$(BOLD)║  API Docs:   http://localhost:8000/api/docs ║$(RESET)"
	@echo "$(GREEN)$(BOLD)║  Grafana:    http://localhost:3001   ║$(RESET)"
	@echo "$(GREEN)$(BOLD)║  Prometheus: http://localhost:9090   ║$(RESET)"
	@echo "$(GREEN)$(BOLD)╚══════════════════════════════════════╝$(RESET)"

.PHONY: down
down: ## Stop all services
	@echo "$(YELLOW)Stopping SentinelTwin stack...$(RESET)"
	@$(COMPOSE) -f $(COMPOSE_FILE) down
	@echo "$(GREEN)✓ All services stopped$(RESET)"

.PHONY: restart
restart: down up ## Restart all services

.PHONY: build
build: ## Build all Docker images
	@echo "$(CYAN)Building Docker images (tag: $(DOCKER_TAG))...$(RESET)"
	@$(COMPOSE) -f $(COMPOSE_FILE) build \
		--build-arg VERSION=$(VERSION) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg GIT_COMMIT=$(GIT_COMMIT)
	@echo "$(GREEN)✓ Images built$(RESET)"

.PHONY: pull
pull: ## Pull latest Docker images
	@$(COMPOSE) -f $(COMPOSE_FILE) pull

.PHONY: logs
logs: ## Stream all container logs
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f --tail=100

.PHONY: logs-backend
logs-backend: ## Stream backend logs only
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f backend

.PHONY: ps
ps: ## Show running containers
	@$(COMPOSE) -f $(COMPOSE_FILE) ps

.PHONY: exec-backend
exec-backend: ## Shell into backend container
	@$(COMPOSE) exec backend bash

.PHONY: exec-postgres
exec-postgres: ## psql into PostgreSQL
	@$(COMPOSE) exec postgres psql -U sentineltwin -d sentineltwin

# ═══════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════

.PHONY: db-migrate
db-migrate: ## Run database migrations
	@echo "$(CYAN)Running database migrations...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/alembic upgrade head
	@echo "$(GREEN)✓ Migrations complete$(RESET)"

.PHONY: db-revision
db-revision: ## Create new migration revision
	@read -p "Migration name: " name; \
	cd $(BACKEND_DIR) && $(VENV_BIN)/alembic revision --autogenerate -m "$$name"

.PHONY: db-rollback
db-rollback: ## Rollback last migration
	@cd $(BACKEND_DIR) && $(VENV_BIN)/alembic downgrade -1

.PHONY: db-seed
db-seed: ## Seed database with test data
	@echo "$(CYAN)Seeding database...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/python scripts/seed_db.py
	@echo "$(GREEN)✓ Database seeded$(RESET)"

.PHONY: db-backup
db-backup: ## Backup PostgreSQL database
	@echo "$(CYAN)Backing up database...$(RESET)"
	@$(COMPOSE) exec postgres pg_dump -U sentineltwin sentineltwin \
		| gzip > $(REPORTS_DIR)/backup_$(shell date +%Y%m%d_%H%M%S).sql.gz
	@echo "$(GREEN)✓ Backup complete$(RESET)"

# ═══════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend test suite
	@echo "$(CYAN)Running backend tests...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest \
		tests/ \
		-v \
		--tb=short \
		--cov=. \
		--cov-report=term-missing \
		--cov-report=html:coverage_html \
		-x
	@echo "$(GREEN)✓ Backend tests complete$(RESET)"

.PHONY: test-frontend
test-frontend: ## Run frontend tests
	@echo "$(CYAN)Running frontend tests...$(RESET)"
	@cd $(FRONTEND_DIR) && npm test -- --watchAll=false

.PHONY: test-integration
test-integration: ## Run integration tests
	@echo "$(CYAN)Running integration tests...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/integration/ -v

.PHONY: test-sensor-engine
test-sensor-engine: ## Run sensor engine unit tests
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/test_sensor_engine.py -v

.PHONY: test-ai-engine
test-ai-engine: ## Run AI engine tests
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/test_ai_engine.py -v

.PHONY: test-hash-chain
test-hash-chain: ## Run hash chain integrity tests
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/test_hash_chain.py -v

.PHONY: test-security
test-security: ## Run security & auth tests
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/test_auth.py tests/test_security.py -v

.PHONY: benchmark
benchmark: ## Run performance benchmark
	@echo "$(CYAN)Running SentinelTwin performance benchmark...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/python scripts/benchmark.py

# ═══════════════════════════════════════════════════════════════
# CODE QUALITY
# ═══════════════════════════════════════════════════════════════

.PHONY: lint
lint: lint-backend lint-frontend ## Lint all code

.PHONY: lint-backend
lint-backend: ## Lint backend Python code
	@echo "$(CYAN)Linting backend...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/ruff check . && $(VENV_BIN)/mypy . --ignore-missing-imports
	@echo "$(GREEN)✓ Backend lint passed$(RESET)"

.PHONY: lint-frontend
lint-frontend: ## Lint frontend TypeScript code
	@cd $(FRONTEND_DIR) && npm run lint

.PHONY: format
format: ## Format all code
	@cd $(BACKEND_DIR) && $(VENV_BIN)/ruff format .
	@cd $(FRONTEND_DIR) && npm run format

.PHONY: type-check
type-check: ## Run type checking
	@cd $(BACKEND_DIR) && $(VENV_BIN)/mypy . --ignore-missing-imports
	@cd $(FRONTEND_DIR) && npm run type-check

# ═══════════════════════════════════════════════════════════════
# REPORTS & AUDIT
# ═══════════════════════════════════════════════════════════════

.PHONY: generate-report
generate-report: ## Generate dispatch readiness report
	@echo "$(CYAN)Generating dispatch report...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/python scripts/generate_report.py
	@echo "$(GREEN)✓ Report generated in $(REPORTS_DIR)/$(RESET)"

.PHONY: verify-chain
verify-chain: ## Verify hash chain integrity
	@echo "$(CYAN)Verifying audit chain integrity...$(RESET)"
	@curl -s http://localhost:8000/api/v1/hashchain/verify \
		-H "Authorization: Bearer $$(cat .token 2>/dev/null || echo TOKEN_NOT_SET)" \
		| python3 -m json.tool

.PHONY: audit-log
audit-log: ## Show recent audit log entries
	@$(COMPOSE) exec postgres psql -U sentineltwin -d sentineltwin \
		-c "SELECT username, action, resource_type, ip_address, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 50;"

# ═══════════════════════════════════════════════════════════════
# CLEAN
# ═══════════════════════════════════════════════════════════════

.PHONY: clean
clean: ## Remove build artifacts and caches
	@echo "$(YELLOW)Cleaning build artifacts...$(RESET)"
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf $(BACKEND_DIR)/htmlcov $(BACKEND_DIR)/.coverage
	@cd $(FRONTEND_DIR) && rm -rf dist .vite 2>/dev/null || true
	@echo "$(GREEN)✓ Clean complete$(RESET)"

.PHONY: clean-all
clean-all: clean ## Remove everything including Docker volumes (DESTRUCTIVE)
	@echo "$(RED)WARNING: This will destroy all data volumes!$(RESET)"
	@read -p "Type 'DELETE' to confirm: " confirm; \
	if [ "$$confirm" = "DELETE" ]; then \
		$(COMPOSE) down -v --remove-orphans; \
		rm -rf $(VENV) $(FRONTEND_DIR)/node_modules; \
		echo "$(GREEN)✓ Full clean complete$(RESET)"; \
	else \
		echo "$(YELLOW)Cancelled$(RESET)"; \
	fi

# ═══════════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════════

.PHONY: security-scan
security-scan: ## Run security vulnerability scan
	@echo "$(CYAN)Running security scan...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/bandit -r . -ll -x tests/
	@cd $(BACKEND_DIR) && $(VENV_BIN)/safety check -r requirements.txt

.PHONY: generate-certs
generate-certs: ## Generate self-signed TLS certificates for development
	@echo "$(CYAN)Generating TLS certificates...$(RESET)"
	@mkdir -p $(INFRA_DIR)/docker/nginx/ssl
	@openssl req -x509 -newkey rsa:4096 -keyout $(INFRA_DIR)/docker/nginx/ssl/key.pem \
		-out $(INFRA_DIR)/docker/nginx/ssl/cert.pem -days 365 -nodes \
		-subj "/CN=sentineltwin.airbus.internal/O=Airbus/C=FR"
	@echo "$(GREEN)✓ TLS certificates generated$(RESET)"

# ═══════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════

.PHONY: metrics
metrics: ## Show live system metrics
	@echo "$(CYAN)SentinelTwin Live Metrics$(RESET)"
	@curl -s http://localhost:8000/api/v1/system/metrics | python3 -m json.tool

.PHONY: health
health: ## Check all service health endpoints
	@echo "$(CYAN)Health Check — SentinelTwin$(RESET)"
	@echo -n "Backend:    "; curl -sf http://localhost:8000/health > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAIL$(RESET)"
	@echo -n "Frontend:   "; curl -sf http://localhost:3000 > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAIL$(RESET)"
	@echo -n "Prometheus: "; curl -sf http://localhost:9090/-/healthy > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAIL$(RESET)"
	@echo -n "Grafana:    "; curl -sf http://localhost:3001/api/health > /dev/null && echo "$(GREEN)OK$(RESET)" || echo "$(RED)FAIL$(RESET)"

.PHONY: status
status: ## Full system status overview
	@echo ""
	@echo "$(BOLD)SENTINELTWIN v$(VERSION) — System Status$(RESET)"
	@echo "$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)"
	@$(MAKE) health
	@echo ""
	@$(MAKE) ps

# ═══════════════════════════════════════════════════════════════
# SEED & SMOKE TESTS
# ═══════════════════════════════════════════════════════════════

.PHONY: seed
seed: ## Seed the database with default users, aircraft, and AI model
	@echo -e "$(CYAN)Seeding database...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/python ../scripts/seed_db.py
	@echo -e "$(GREEN)✓ Database seeded$(RESET)"

.PHONY: smoke
smoke: ## Run the smoke test suite against a running backend
	@echo -e "$(CYAN)Running smoke tests...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/python _smoke_test.py

.PHONY: e2e
e2e: ## Run full end-to-end test suite (requires running backend)
	@echo -e "$(CYAN)Running E2E tests...$(RESET)"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/test_e2e.py -v --timeout=30

.PHONY: test-unit
test-unit: ## Run unit tests only (fast)
	@cd $(BACKEND_DIR) && $(VENV_BIN)/pytest tests/test_suite.py -v

# ═══════════════════════════════════════════════════════════════
# EXTENDED DOCKER
# ═══════════════════════════════════════════════════════════════

.PHONY: rebuild
rebuild: ## Rebuild Docker images and restart (no cache)
	@$(COMPOSE) -f $(COMPOSE_FILE) build --no-cache \
		--build-arg VERSION=$(VERSION) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg GIT_COMMIT=$(GIT_COMMIT)
	@$(COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo -e "$(GREEN)✓ Rebuilt and restarted$(RESET)"

.PHONY: logs-frontend
logs-frontend: ## Tail frontend/nginx logs
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f frontend --tail=100

# ═══════════════════════════════════════════════════════════════
# EXTENDED DATABASE
# ═══════════════════════════════════════════════════════════════

.PHONY: db-reset
db-reset: ## Drop and recreate the database (DESTRUCTIVE)
	@echo -e "$(RED)WARNING: This will destroy all data. Press Ctrl+C within 5s to cancel.$(RESET)"
	@sleep 5
	@$(COMPOSE) exec postgres psql -U sentineltwin -c "DROP DATABASE IF EXISTS sentineltwin;"
	@$(COMPOSE) exec postgres psql -U sentineltwin -c "CREATE DATABASE sentineltwin;"
	@cd $(BACKEND_DIR) && $(VENV_BIN)/alembic upgrade head
	@$(MAKE) seed
	@echo -e "$(GREEN)✓ Database reset and reseeded$(RESET)"

# ═══════════════════════════════════════════════════════════════
# QUALITY (combined)
# ═══════════════════════════════════════════════════════════════

.PHONY: quality
quality: lint type-check security-scan ## Run all backend quality checks (lint + types + security)

# ═══════════════════════════════════════════════════════════════
# EXTENDED FRONTEND
# ═══════════════════════════════════════════════════════════════

.PHONY: fe-build
fe-build: ## Build frontend for production
	@echo -e "$(CYAN)Building frontend...$(RESET)"
	@cd $(FRONTEND_DIR) && npm run build
	@echo -e "$(GREEN)✓ Frontend built$(RESET)"

.PHONY: fe-quality
fe-quality: lint-frontend ## All frontend quality checks

# ═══════════════════════════════════════════════════════════════
# KUBERNETES
# ═══════════════════════════════════════════════════════════════

.PHONY: k8s-apply
k8s-apply: ## Apply Kubernetes manifests to current context
	@echo -e "$(CYAN)Applying K8s manifests...$(RESET)"
	@kubectl apply -f $(INFRA_DIR)/k8s/sentineltwin.yml
	@echo -e "$(GREEN)✓ K8s manifests applied$(RESET)"

.PHONY: k8s-delete
k8s-delete: ## Remove Kubernetes resources
	@kubectl delete -f $(INFRA_DIR)/k8s/sentineltwin.yml --ignore-not-found

.PHONY: k8s-status
k8s-status: ## Show pod and service status in sentineltwin namespace
	@kubectl get pods,svc,hpa -n sentineltwin

.PHONY: k8s-logs
k8s-logs: ## Tail backend pod logs
	@kubectl logs -n sentineltwin -l app=sentineltwin-backend -f --tail=100

.PHONY: k8s-rollout
k8s-rollout: ## Check rollout status
	@kubectl rollout status deployment/sentineltwin-backend -n sentineltwin

# ═══════════════════════════════════════════════════════════════
# EXTENDED OPERATIONS
# ═══════════════════════════════════════════════════════════════

.PHONY: health-detailed
health-detailed: ## Check detailed health (auto-acquires JWT)
	@TOKEN=$$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
		-H "Content-Type: application/json" \
		-d '{"username":"admin","password":"sentinel2026"}' \
		| $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") && \
	curl -sf http://localhost:8000/health \
		-H "Authorization: Bearer $$TOKEN" | $(PYTHON) -m json.tool

.PHONY: download-report
download-report: ## Download a PDF airworthiness report via curl
	@mkdir -p $(REPORTS_DIR)
	@TOKEN=$$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
		-H "Content-Type: application/json" \
		-d '{"username":"admin","password":"sentinel2026"}' \
		| $(PYTHON) -c "import sys,json;print(json.load(sys.stdin)['access_token'])") && \
	curl -sf http://localhost:8000/api/v1/reports/generate \
		-H "Authorization: Bearer $$TOKEN" \
		-o $(REPORTS_DIR)/sentineltwin-report-$$(date +%Y%m%dT%H%M%S).pdf && \
	echo -e "$(GREEN)✓ Report saved to $(REPORTS_DIR)/$(RESET)"

# ═══════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════

.PHONY: init
init: ## First-time setup: install deps, run migrations, seed DB
	@echo -e "$(CYAN)$(BOLD)SentinelTwin — First-time initialization$(RESET)"
	@$(MAKE) setup
	@$(COMPOSE) up -d postgres redis
	@echo -e "$(CYAN)Waiting for infrastructure...$(RESET)"
	@sleep 5
	@$(MAKE) db-migrate
	@$(MAKE) seed
	@echo ""
	@echo -e "$(GREEN)$(BOLD)╔══════════════════════════════════════════╗$(RESET)"
	@echo -e "$(GREEN)$(BOLD)║  ✓ Initialization complete               ║$(RESET)"
	@echo -e "$(GREEN)$(BOLD)║  Run 'make dev' to start development     ║$(RESET)"
	@echo -e "$(GREEN)$(BOLD)╚══════════════════════════════════════════╝$(RESET)"

