# =============================================================================
# zrun-backend Task Automation
# =============================================================================
# Production-grade Python monorepo for zrun microservices.
#
# Usage:
#   just <recipe>        # List all available recipes
#   just init           # Initialize workspace
#   just run zrun-base  # Run a service
# =============================================================================

default:
    @just --list

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
# VALIDATION (INTERNAL)
# =============================================================================

# Validate service exists and show available services (internal use)
_validate-service service:
    #!/usr/bin/env bash
    set -e
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"

    # Check if service directory exists
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
# SERVICE INFORMATION
# =============================================================================

# List all available services with their status
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

    # Check if service exists
    if [ ! -d "$SERVICE_DIR" ]; then
        echo "Status: ❌ Not found"
        exit 1
    fi

    # Check main.py
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

# =============================================================================
# PROTOCOL BUFFERS
# =============================================================================

# Compile proto files to Python code
proto:
    @echo "==> Compiling proto files..."
    uv run python shared/zrun-schema/scripts/compile_protos.py
    @echo "==> Post-processing generated code..."
    uv run python shared/zrun-schema/scripts/post_gen.py

# Lint proto files (requires buf)
proto-lint:
    @echo "==> Linting proto files..."
    buf lint

# Format proto files (requires buf)
proto-format:
    @echo "==> Formatting proto files..."
    buf format -w

# Check proto format without making changes
proto-format-check:
    @echo "==> Checking proto file format..."
    buf format --diff

# Check for breaking changes (requires buf, compares against main branch)
proto-breaking:
    #!/usr/bin/env bash
    if [ -d .git ]; then
        echo "==> Checking for breaking changes..."
        buf breaking --against '.git#branch=main'
    else
        echo "==> Skipping breaking change check (not a git repository)"
    fi

# Run all proto checks (lint + format + breaking)
proto-check:
    #!/usr/bin/env bash
    just proto-lint || exit 1
    just proto-format-check || exit 1
    just proto-breaking || exit 1
    echo "==> All proto checks passed"

# =============================================================================
# SERVICE MANAGEMENT
# =============================================================================

# Run a service with default database (PostgreSQL)
run service:
    #!/usr/bin/env bash
    set -e
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"
    MODULE_NAME=${SERVICE//-/_}

    # Validate service exists
    just _validate-service {{service}}

    # Check for DATABASE_URL
    if [ -z "$DATABASE_URL" ] && [ -z "$POSTGRES_URL" ]; then
        echo "⚠ Warning: DATABASE_URL not set, using SQLite for development"
        export DATABASE_BACKEND=sqlite
    fi

    echo "==> Starting $SERVICE..."
    cd "$SERVICE_DIR" && uv run python -m "$MODULE_NAME".main

# Run a service with SQLite (for development/testing)
dev service:
    #!/usr/bin/env bash
    set -e
    SERVICE="{{service}}"
    SERVICE_DIR="services/$SERVICE"
    MODULE_NAME=${SERVICE//-/_}

    # Validate service exists
    just _validate-service {{service}}

    echo "==> Starting $SERVICE (SQLite backend)..."
    cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run python -m "$MODULE_NAME".main

# =============================================================================
# TESTING
# =============================================================================

# Run all checks for a service (lint, format, type, tests)
test service:
    #!/usr/bin/env bash
    SERVICE="{{service}}"

    # Validate service exists
    just _validate-service {{service}}

    SERVICE_DIR="services/$SERVICE"

    echo ""
    echo "==> Testing $SERVICE"
    echo "   Ruff check..."
    cd "$SERVICE_DIR" && uv run ruff check . || exit 1

    echo "   Ruff format check..."
    cd "$SERVICE_DIR" && uv run ruff format --check . || exit 1

    echo "   Mypy type check..."
    cd "$SERVICE_DIR" && uv run mypy . || exit 1

    echo "   Pytest (SQLite)..."
    cd "$SERVICE_DIR" && DATABASE_BACKEND=sqlite uv run pytest || exit 1

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
# CODE QUALITY
# =============================================================================

# Format code with ruff
format:
    @echo "==> Formatting code..."
    uv run ruff format .

# Check code format without making changes
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

# Type check with mypy
typecheck:
    @echo "==> Type checking..."
    uv run mypy .

# Run all quality checks (format, lint, type, proto)
check: format-check lint typecheck proto-check

# =============================================================================
# BUILD & CLEANUP
# =============================================================================

# Clean all generated and cache files
clean:
    @echo "==> Cleaning generated files..."
    rm -rf shared/zrun-schema/src/zrun_schema/generated/*.py
    rm -rf shared/zrun-schema/src/zrun_schema/generated/base/
    rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
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
# DEVELOPMENT HELPERS
# =============================================================================

# Show this project's architecture
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
    @echo "│   ├── zrun-base/      # Core business service"
    @echo "│   ├── zrun-stock/     # Stock management"
    @echo "│   ├── zrun-ops/        # Operations"
    @echo "│   ├── zrun-integration/  # Third-party integrations"
    @echo "│   └── zrun-analytics/  # Analytics"
    @echo "└── scripts/"

# Show quick reference for common commands
help:
    @echo "Quick Reference:"
    @echo ""
    @echo "Setup:"
    @echo "  just init           # Initialize workspace"
    @echo "  just proto          # Compile proto files"
    @echo ""
    @echo "Proto Quality:"
    @echo "  just proto-lint     # Lint proto files"
    @echo "  just proto-format   # Format proto files"
    @echo "  just proto-check    # Run all proto checks"
    @echo ""
    @echo "Services:"
    @echo "  just list           # List all services"
    @echo "  just run <service>   # Run service (default: PostgreSQL)"
    @echo "  just dev <service>   # Run service (SQLite for dev)"
    @echo ""
    @echo "  Environment Variables:"
    @echo "  DATABASE_URL       # PostgreSQL connection string"
    @echo "  DATABASE_BACKEND   # Override: postgresql or sqlite"
    @echo ""
    @echo "Testing:"
    @echo "  just test <service> # Full test suite (SQLite)"
    @echo "  just test-unit <service>  # Unit tests only"
    @echo "  just test-cov <service>  # With coverage"
    @echo ""
    @echo "Quality:"
    @echo "  just format         # Format code"
    @echo "  just lint          # Lint code"
    @echo "  just typecheck     # Type check"
    @echo "  just check         # Run all checks"
    @echo ""
    @echo "Cleanup:"
    @echo "  just clean          # Clean generated files"
    @echo "  just rebuild        # Rebuild from scratch"

# =============================================================================
# ALIASES (shortcuts)
# =============================================================================

# Alias for list-services
ls: list

# Alias for test
t service:
    just test {{service}}
