# =============================================================================
# zrun-backend Task Automation
# =============================================================================
# Production-grade Python monorepo for zrun microservices.
#
# Quick Start:
#   just init           # Initialize workspace
#   just proto          # Compile proto files
#   just dev zrun-base  # Run a service (SQLite)
#   just test zrun-base # Run tests
# =============================================================================

default:
    @just --list

# =============================================================================
# INTERNAL (Utilities used by other recipes)
# =============================================================================

# Validate service exists (internal use)
_validate-service service:
    #!/usr/bin/env bash
    set -e
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"

    if [ ! -d "$SERVICE_DIR" ]; then
        echo "❌ Error: Service '$SERVICE' not found"
        echo ""
        echo "Available services:"
        for dir in services/*/; do
            if [ -d "$dir" ]; then
                name=$(basename "$dir")
                module_name=${name//-/_}
                if [ -f "$dir/src/$module_name/main.py" ]; then
                    echo "  • $name (ready)"
                else
                    echo "  • $name (no main.py)"
                fi
            fi
        done
        exit 1
    fi

# =============================================================================
# SETUP & INSTALLATION
# =============================================================================

# Initialize the workspace (sync all packages)
init:
    @echo "==> Initializing workspace..."
    uv sync --all-packages

# Install development dependencies
install-dev:
    @echo "==> Installing development dependencies..."
    uv add --dev -o pyproject.toml mypy ruff pytest pytest-asyncio pytest-cov

# =============================================================================
# PROTOCOL BUFFERS
# =============================================================================

# Compile proto files to Python code
proto:
    @echo "==> Compiling proto files..."
    buf generate shared/zrun-schema/protos --template shared/zrun-schema/buf.gen.yaml
    @echo "==> Post-processing generated code..."
    uv run python shared/zrun-schema/scripts/post_gen.py

# Lint proto files
proto-lint:
    @echo "==> Linting proto files..."
    buf lint

# Format proto files
proto-format:
    @echo "==> Formatting proto files..."
    buf format -w

# Check proto format without changes
proto-format-check:
    @echo "==> Checking proto format..."
    buf format --diff

# Check for breaking changes against main branch
proto-breaking:
    #!/usr/bin/env bash
    if [ -d .git ]; then
        echo "==> Checking for breaking changes..."
        buf breaking --against '.git#branch=main'
    else
        echo "==> Skipping breaking change check (not a git repository)"
    fi

# Run all proto checks
proto-check: proto-lint proto-format-check proto-breaking
    @echo "==> All proto checks passed"

# =============================================================================
# SERVICE MANAGEMENT
# =============================================================================

# List all available services
list:
    #!/usr/bin/env bash
    echo "Services:"
    for dir in services/*/; do
        if [ -d "$dir" ]; then
            name=$(basename "$dir")
            module_name=${name//-/_}
            if [ -f "$dir/src/$module_name/main.py" ]; then
                echo "  • $name (ready)"
            else
                echo "  • $name (not implemented)"
            fi
        fi
    done

# Show detailed information about a service
info service:
    #!/usr/bin/env bash
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"
    MODULE_NAME=${SERVICE//-/_}

    echo "Service: $SERVICE"
    echo "Module: $MODULE_NAME"
    echo ""

    if [ ! -d "$SERVICE_DIR" ]; then
        echo "Status: ❌ Not found"
        exit 1
    fi

    if [ -f "$SERVICE_DIR/src/$MODULE_NAME/main.py" ]; then
        echo "Status: ✓ Ready"
        echo ""
        echo "Files:"
        [ -f "$SERVICE_DIR/pyproject.toml" ] && echo "  • pyproject.toml"
        [ -d "$SERVICE_DIR/src/$MODULE_NAME" ] && echo "  • src/$MODULE_NAME/"
        [ -d "$SERVICE_DIR/tests" ] && echo "  • tests/"
    else
        echo "Status: ⚠ Not implemented"
    fi

# Run a service (PostgreSQL by default, falls back to SQLite)
run service:
    #!/usr/bin/env bash
    set -e
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"
    MODULE_NAME=${SERVICE//-/_}

    just _validate-service {{service}}

    if [ -z "$DATABASE_URL" ] && [ -z "$POSTGRES_URL" ]; then
        echo "⚠ Warning: DATABASE_URL not set, using SQLite for development"
        export DATABASE_BACKEND=sqlite
    fi

    echo "==> Starting $SERVICE..."
    cd "$SERVICE_DIR" && uv run python -m "$MODULE_NAME".main

# Run a service with SQLite (for development)
dev service:
    #!/usr/bin/env bash
    set -e
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"
    MODULE_NAME=${SERVICE//-/_}

    just _validate-service {{service}}
    echo "==> Starting $SERVICE (SQLite backend)..."
    cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run python -m "$MODULE_NAME".main

# =============================================================================
# CODE QUALITY
# =============================================================================

# Format code with ruff
format:
    @echo "==> Formatting code..."
    uv run ruff format .

# Check code format without changes
format-check:
    @echo "==> Checking code format..."
    uv run ruff format --check .

# Lint code with ruff
lint:
    @echo "==> Linting code..."
    uv run ruff check .

# Fix linting issues automatically
lint-fix:
    @echo "==> Fixing linting issues..."
    uv run ruff check --fix .

# Type check with basedpyright (core packages only)
typecheck:
    @echo "==> Type checking..."
    uv run basedpyright services/*/src shared/*/src

# Run all quality checks (format, lint, type, proto)
check: format-check lint typecheck proto-check
    @echo "==> All checks passed"

# =============================================================================
# TESTING
# =============================================================================

# Run all tests for a service (lint + format + type + pytest)
test service:
    #!/usr/bin/env bash
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"

    just _validate-service {{service}}

    echo ""
    echo "==> Testing $SERVICE"
    echo "   Ruff check..." && (cd "$SERVICE_DIR" && uv run ruff check .) || exit 1
    echo "   Ruff format check..." && (cd "$SERVICE_DIR" && uv run ruff format --check .) || exit 1
    echo "   Basedpyright type check..." && (cd "$SERVICE_DIR" && uv run basedpyright .) || exit 1
    echo "   Pytest (SQLite)..." && (cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run pytest) || exit 1

    echo ""
    echo "✓ All tests passed for $SERVICE"

# Run unit tests only
test-unit service:
    #!/usr/bin/env bash
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"

    just _validate-service {{service}}
    cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run pytest tests/unit/ -v

# Run integration tests only
test-integration service:
    #!/usr/bin/env bash
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"

    just _validate-service {{service}}
    cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run pytest tests/integration/ -v

# Run tests with coverage report
test-cov service:
    #!/usr/bin/env bash
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"

    just _validate-service {{service}}
    cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run pytest --cov=src --cov-report=html --cov-report=term

# =============================================================================
# BUILD & CLEANUP
# =============================================================================

# Clean all generated and cache files
clean:
    @echo "==> Cleaning generated files..."
    rm -rf shared/zrun-schema/src/zrun_schema/generated/*.py
    rm -rf shared/zrun-schema/src/zrun_schema/generated/base/
    @fd -t d -H "__pycache__|.pytest_cache|.ruff_cache|.mypy_cache|htmlcov" -x rm -rf {} 2>/dev/null || true
    @fd -t f -H ".coverage" -x rm -f {} 2>/dev/null || true
    @fd -t f "\.pyc$" -x rm -f {} 2>/dev/null || true
    @echo "==> Clean complete"

# Deep clean (remove virtual environment)
deep-clean: clean
    @echo "==> Removing virtual environment..."
    rm -rf .venv .uv
    @echo "==> Deep clean complete"

# Rebuild everything from scratch
rebuild: deep-clean init proto
    @echo "==> Rebuild complete"

# =============================================================================
# HELPERS
# =============================================================================

# Show project architecture
arch:
    @echo "Architecture:"
    @echo ""
    @echo "Database Backends:"
    @echo "  • SQLite     - Testing/Development (fast, no external deps)"
    @echo "  • PostgreSQL - Production (reliable, scalable)"
    @echo ""
    @echo "zrun-backend/"
    @echo "├── shared/"
    @echo "│   ├── zrun-core/       # Infrastructure (auth, logging, locking)"
    @echo "│   └── zrun-schema/     # Proto definitions & generated code"
    @echo "├── services/"
    @echo "│   ├── zrun-base/      # Core business service (SKU management)"
    @echo "│   ├── zrun-stock/     # Stock management"
    @echo "│   ├── zrun-ops/       # Operations"
    @echo "│   ├── zrun-integration/ # Third-party integrations"
    @echo "│   └── zrun-analytics/ # Analytics"

# Show quick reference for common commands
help:
    @echo "Quick Reference:"
    @echo ""
    @echo "Setup:"
    @echo "  just init           # Initialize workspace"
    @echo "  just install-dev    # Install dev dependencies"
    @echo ""
    @echo "Proto:"
    @echo "  just proto          # Compile proto files"
    @echo "  just proto-check    # Run all proto checks"
    @echo ""
    @echo "Services:"
    @echo "  just list           # List all services"
    @echo "  just info <svc>     # Show service details"
    @echo "  just dev <svc>      # Run service (SQLite)"
    @echo "  just run <svc>      # Run service (PostgreSQL)"
    @echo ""
    @echo "Quality:"
    @echo "  just format         # Format code"
    @echo "  just lint           # Lint code"
    @echo "  just typecheck      # Type check"
    @echo "  just check          # Run all checks"
    @echo ""
    @echo "Testing:"
    @echo "  just test <svc>     # Full test suite"
    @echo "  just test-unit <svc>   # Unit tests only"
    @echo "  just test-integration <svc> # Integration tests"
    @echo "  just test-cov <svc>     # With coverage"
    @echo ""
    @echo "Environment Variables:"
    @echo "  DATABASE_URL       # PostgreSQL connection string"
    @echo "  DATABASE_BACKEND   # Override: postgresql or sqlite"
    @echo ""
    @echo "Cleanup:"
    @echo "  just clean          # Clean generated files"
    @echo "  just rebuild        # Rebuild from scratch"

# =============================================================================
# ALIASES
# =============================================================================

# Alias for list
ls: list

# Alias for test
t service:
    just test {{service}}

# =============================================================================
# CONTAINER (Docker)
# =============================================================================

# Build base image (only needed when Python/system deps change)
docker-build-base:
    @echo "==> Building base image..."
    docker build -f docker/Dockerfile.base -t zrun-base-image:latest .

# Build a service container image
docker-build service:
    @echo "==> Building {{service}}..."
    docker build -f docker/Dockerfile --build-arg SERVICE={{service}} -t {{service}}:latest .

# Build all service containers (includes base image)
docker-build-all: docker-build-base
    @echo "==> Building all services..."
    @for svc in zrun-base zrun-stock zrun-ops zrun-integration zrun-analytics; do \
        echo "Building $$svc..."; \
        docker build -f docker/Dockerfile --build-arg SERVICE=$$svc -t $$svc:latest .; \
    done

# Push image to registry (requires REGISTRY env var)
docker-push service:
    @echo "==> Pushing {{service}} to ${REGISTRY}..."
    @if [ -z "$$REGISTRY" ]; then echo "Error: REGISTRY env var not set"; exit 1; fi
    docker tag {{service}}:latest ${REGISTRY}/{{service}}:latest
    docker push ${REGISTRY}/{{service}}:latest

# Clean up docker resources
docker-clean:
    @echo "==> Cleaning docker resources..."
    docker system prune -f
    docker image prune -f

# =============================================================================
# VERSION MANAGEMENT
# =============================================================================

# Sync version across all packages (reads from root pyproject.toml)
version-sync:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "==> Syncing versions across all packages..."
    ROOT_VER=$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
    echo "Root version: $ROOT_VER"
    for f in shared/*/pyproject.toml services/*/pyproject.toml; do
        sed -i "s/^version = .*/version = \"$ROOT_VER\"/" "$f"
        echo "Updated: $f"
    done

# Show versions across all packages
version-check:
    @echo "=== All package versions ==="
    @rg "^version" pyproject.toml shared/*/pyproject.toml services/*/pyproject.toml 2>/dev/null | sort
