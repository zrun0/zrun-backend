# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production-grade Python monorepo for zrun microservices using gRPC for inter-service communication. The project uses uv workspaces and follows strict code quality standards (mypy strict mode, comprehensive linting).

**Key Tech Stack:** Python 3.14+, uv (workspaces), gRPC/asyncio, structlog, pytest, ruff, mypy, protoc

---

## Common Development Commands

### Workspace Setup
```bash
just init              # Initialize workspace (sync all packages)
just proto             # Compile proto files (run after .proto changes)
```

### Service Operations
```bash
just run <service>    # Run service with PostgreSQL (requires DATABASE_URL)
just dev <service>    # Run service with SQLite (for development/testing)
just list             # List all services and their status
```

### Quality Checks (run from root)
```bash
just format           # Auto-format code with ruff
just format-check     # Check code format without changes
just lint             # Lint code with ruff
just lint-fix         # Auto-fix linting issues
just typecheck        # Type check with mypy
just check            # Run all checks (format + lint + type)
```

### Testing (per-service)
```bash
just test <service>           # Full test suite (checks + tests)
just test-unit <service>     # Unit tests only
just test-integration <service>  # Integration tests only
just test-cov <service>      # With coverage report

# Direct pytest (from service directory):
uv run pytest tests/unit/ -v                    # Unit tests
uv run pytest tests/integration/ -v               # Integration tests
uv run pytest tests/unit/test_sku_logic.py::TestSkuLogic::test_create_sku_success -v  # Single test
```

### Database Backend Control
```bash
# Services default to SQLite for development
DATABASE_BACKEND=sqlite just dev zrun-base

# For production, set DATABASE_URL for PostgreSQL
DATABASE_URL="postgresql://..." just run zrun-base
```

---

## Architecture

### Monorepo Structure
```
zrun-backend/
├── shared/
│   ├── zrun-core/       # Infrastructure: auth, logging, errors, lock, server
│   └── zrun-schema/     # Proto definitions & generated code
├── services/
│   ├── zrun-base/      # Core business service (SKU management - MVP)
│   ├── zrun-stock/     # Stock management
│   ├── zrun-ops/       # Operations
│   ├── zrun-integration/# Third-party integrations
│   └── zrun-analytics/ # Analytics
└── scripts/            # Root-level utility scripts
```

### Layered Architecture (Per Service)

Each service follows a strict layered architecture:

```
<service>/
├── src/<service>/
│   ├── api/            # gRPC servicers (entry point, converts proto ↔ domain)
│   ├── logic/          # Business logic + domain objects (validation, rules)
│   ├── repository/     # Persistence layer (SQL databases)
│   └── main.py         # Service entry point
└── tests/
    ├── unit/           # Isolated logic/repository tests
    └── integration/    # Tests with mock gRPC context
```

**Key Patterns:**

1. **Servicer Layer (`api/`)**: Handles gRPC concerns only
   - Extracts user context from gRPC context
   - Converts protobuf ↔ domain objects
   - Calls logic layer
   - Uses `abort_with_error()` for error handling

2. **Logic Layer (`logic/`)**: Pure business rules
   - Contains frozen `@dataclass` domain objects
   - Validation logic in `domain.validate()` methods
   - Depends on `SkuRepository` protocol (not concrete implementations)

3. **Repository Layer (`repository/`)**: Data persistence
   - Protocol-based design: `SkuRepository` Protocol defines interface
   - Implementations: `PostgresSkuRepository`, `SqliteSkuRepository`, `MockSkuRepository`
   - All database operations use proper timezone-aware `datetime`

### Inter-Service Communication

**CRITICAL:** Services NEVER import each other directly. All inter-service communication MUST go through gRPC:
- Proto definitions in `shared/zrun-schema/protos/` (single source of truth)
- Generated code in `shared/zrun-schema/src/zrun_schema/generated/`
- Import pattern: `from zrun_schema.generated.base import sku_pb2 as base_sku_pb2`

### Error Handling

Use the error hierarchy from `zrun_core.errors`:
- `ValidationError`: Input validation failures (returns INVALID_ARGUMENT)
- `NotFoundError`: Resource not found (returns NOT_FOUND)
- `ConflictError`: Resource already exists (returns ALREADY_EXISTS)
- `AuthenticationError`: Auth failures (returns UNAUTHENTICATED)
- `AuthorizationError`: Permission denied (returns PERMISSION_DENIED)

**Pattern:** Assign exception messages to variables before raising (EM101/EM102 lint rules):
```python
msg = f"SKU with code '{code}' already exists"
raise ConflictError(msg)
```

### Domain Objects

- Always use `frozen=True` dataclasses for immutability
- Include `validate()` method for self-validation
- Use `datetime.now(UTC)` instead of `datetime.utcnow()`
- Store timestamps as milliseconds (int64) in proto, convert to `datetime` in domain

### Proto File Workflow

1. Edit `.proto` files in `shared/zrun-schema/protos/`
2. Run `just proto` to generate:
   - `*_pb2.py` (messages)
   - `*_pb2_grpc.py` (gRPC services)
   - Post-processing script fixes import paths
3. Import from services: `from zrun_schema.generated.base import sku_pb2 as base_sku_pb2`

**IMPORTANT:** After proto compilation, `generated/base/__init__.py` may be deleted by clean operations. Recreate it if needed to fix import issues.

---

## Code Quality Standards

### Type Checking
- **strict mode** enabled in `pyproject.toml`
- Test files excluded from strict checking (but still type-checked)
- Use `TYPE_CHECKING` blocks for imports only used in type hints
- Proto generated code excluded from type checking

### Linting (ruff)
Key enabled rules:
- **EM101/EM102:** Exception string literals must be assigned to variables first
- **DTZ003/DTZ006:** Always use timezone-aware datetime (`datetime.now(UTC)`, `datetime.fromtimestamp(..., tz=UTC)`)
- **N802:** gRPC methods use PascalCase (protobuf convention)
- **ARG001:** Unused function arguments allowed in structlog processors (part of API)
- **TCH:** Type-checking block suggestions (use judgment - some are false positives for runtime imports)

### Import Organization
- Known first-party: `zrun_core`, `zrun_schema`, `zrun_base`, `zrun_stock`, etc.
- Use `from __future__ import annotations` at top of every file
- Third-party imports (grpc, structlog, etc.) should be at module level, not nested in functions

---

## Important Conventions

### Naming
- Service directories: `zrun-*` (kebab-case)
- Module names: `zrun_*` (snake_case) - hyphens converted to underscores
- gRPC methods: PascalCase (protobuf convention)
- Test fixtures: pytest fixtures with descriptive names

### Timezone Handling
**Always use UTC for datetimes:**
```python
from datetime import UTC, datetime

now = datetime.now(UTC)  # Correct
created_at = datetime.fromtimestamp(ms / 1000, tz=UTC)  # Correct
```

### Async/Await
- All repository methods are async
- All servicer methods are async
- Use `DATABASE_BACKEND=sqlite` for testing (in-memory SQLite)
- Use pytest-asyncio with `asyncio_mode="auto"`

### Test Structure
- `tests/unit/`: Tests for individual components (logic, repository) without external dependencies
- `tests/integration/`: Tests with mock gRPC context, tests servo layer
- Use `MockServicerContext` in integration tests (creates `MockRpcError` on `abort()`)
- Fixtures in `tests/conftest.py`: `test_db`, `sku_repo`, `sku_logic`, `sku_servicer`

---

## Database Backends

### SQLite (Development/Testing)
- Default for development
- In-memory: `get_in_memory_connection()` from `zrun_base.repository.sqlite`
- Schema creation: `await create_sku_table(conn)`
- **Limitation:** Multiple SQL statements must be executed separately (SQLite limitation)

### PostgreSQL (Production)
- Set `DATABASE_URL` environment variable
- Connection pooling via `asyncpg.create_pool()`
- Schema creation: `await create_postgres_sku_table(pool)`

---

## Troubleshooting

### Proto Import Errors
If you see `ModuleNotFoundError: No module named 'common_pb2'`:
1. Run `just proto` to regenerate
2. Check `generated/base/__init__.py` exists (may need to recreate after clean)

### Type Check Failures in Tests
- Test files have relaxed mypy settings but still enforce basic type safety
- Mock objects may need `# type: ignore` for intentionally untyped attributes

### Format Issues After Proto Compilation
- Run `just format` to auto-format
- Generated proto files excluded from format checks

### Lint False Positives
- **TC001/TC002/TC003** (type-checking block): These are often false positives for imports used at runtime
- **ARG001** (unused arguments): Acceptable for structlog processor functions (`_logger`, `_method_name`)
- Use judgment before "fixing" these - many are intentional
