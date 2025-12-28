# ============================================================================
# Odiseo MCP Server - Makefile
# ============================================================================
# Convenient commands for development and Docker operations
#
# Usage:
#   make help          Show available commands
#   make build         Build Docker image
#   make up            Start services
#   make down          Stop services
#   make logs          View logs
# ============================================================================

.PHONY: help build up down logs restart shell clean lint format test health

# Default target
.DEFAULT_GOAL := help

# Variables
IMAGE_NAME := mcp-server
CONTAINER_NAME := mcp-server
COMPOSE_FILE := docker-compose.yml

# ============================================================================
# Help
# ============================================================================
help: ## Show this help message
	@echo "Odiseo MCP Server - Available Commands"
	@echo "======================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Docker Operations
# ============================================================================
build: ## Build Docker image
	docker compose build

build-no-cache: ## Build Docker image without cache
	docker compose build --no-cache

up: ## Start services in detached mode
	docker compose up -d

up-logs: ## Start services with logs
	docker compose up

down: ## Stop and remove services
	docker compose down

restart: down up ## Restart services

logs: ## View service logs (follow mode)
	docker compose logs -f mcp

logs-tail: ## View last 100 log lines
	docker compose logs --tail=100 mcp

shell: ## Open shell in running container
	docker compose exec mcp /bin/bash

# ============================================================================
# Installation (using uv - 10-100x faster than pip)
# ============================================================================
install-uv: ## Install uv package manager
	curl -LsSf https://astral.sh/uv/install.sh | sh

install: ## Install dependencies with uv
	uv pip install --system -r requirements.txt

install-dev: ## Install dev dependencies with uv
	uv pip install --system -r requirements.txt ruff pytest mypy bandit

# ============================================================================
# Development
# ============================================================================
lint: ## Run ruff linter
	ruff check .

format: ## Format code with ruff
	ruff format .

check: lint ## Run all checks
	ruff check .
	python -m py_compile server.py

test: ## Run tests (requires pytest)
	pytest tests/ -v

# ============================================================================
# Health & Status
# ============================================================================
health: ## Check service health
	@curl -s http://localhost:8009/health | python -m json.tool || echo "Service not running"

status: ## Show container status
	docker compose ps

# ============================================================================
# Cleanup
# ============================================================================
clean: ## Remove containers, images, and volumes
	docker compose down -v --rmi local

clean-logs: ## Remove log files
	rm -rf logs/*.log

clean-pycache: ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-all: clean clean-logs clean-pycache ## Remove everything

# ============================================================================
# Network Setup
# ============================================================================
network-create: ## Create docker-config network
	docker network create docker-config 2>/dev/null || echo "Network already exists"

network-inspect: ## Inspect docker-config network
	docker network inspect docker-config

# ============================================================================
# Environment
# ============================================================================
env-setup: ## Copy .env.example to .env
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env file created from .env.example"; \
		echo "Please edit .env with your configuration"; \
	else \
		echo ".env file already exists"; \
	fi

env-check: ## Validate required environment variables
	@echo "Checking required environment variables..."
	@test -n "$$GOOGLE_API_KEY" || (echo "ERROR: GOOGLE_API_KEY not set" && exit 1)
	@test -n "$$DATABASE_URL" || test -n "$$POSTGRES_PASSWORD" || (echo "ERROR: DATABASE_URL or POSTGRES_PASSWORD not set" && exit 1)
	@echo "All required variables are set"
