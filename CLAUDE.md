# Zrun WMS Development Standards

> This document provides strict architectural guidance for [Claude Code](https://claude.ai/code) when developing **Zrun SaaS WMS** — a production-grade Python monorepo backend. All code contributions must adhere to the service boundaries and quality standards defined in this document.

---

## Table of Contents

1. [Project Vision & Design Philosophy](#1-project-vision--design-philosophy)
2. [Architectural Standards](#2-architectural-standards)
3. [Code Quality Standards](#3-code-quality-standards)
4. [Development Workflow](#4-development-workflow)

---

## 1. Project Vision & Design Philosophy

Zrun's core goal is **complexity convergence**. Every code contribution must strictly respect service boundaries to prevent business logic decay.

### 1.1 Service Boundaries

| Service | Responsibility | Hard Constraints |
|---|---|---|
| **Base** | Core master data & rules (tenants, SKUs, locations) | No inventory handling, no order processing |
| **Stock** | Inventory: single source of truth, strong consistency | No business logic, no external calls |
| **Ops** | Business state machines (inbound, outbound, waves, picking) | Must drive Stock — never manipulate quantities directly |
| **Integration** | External adapters (ERP / 3PL / WCS) | Engineering reliability only — no business logic |
| **Analytics** | Read-only reporting layer | Must not affect live operations or write to business DB |
| **BFF** | OAuth2 authentication + JWT re-issuance for internal services | Issues internal JWTs, aggregates APIs, translates HTTP → gRPC |

### 1.2 Dependency Direction

```
Ops → Stock (synchronous, strongly consistent)
Ops ↔ Integration (async, event-driven)
BFF → All Services (via gRPC)
```

---

## 2. Architectural Standards

### 2.1 Cross-Service Rules ⚠️ CRITICAL

> PRs that violate these rules will be rejected without review.

- **No direct imports** across services (e.g., `zrun-ops` must never import `zrun-stock`)
- **gRPC is the only interface** — all cross-service calls go through `zrun-schema`
- **Layered architecture** — each service follows Servicer → Logic → Repository pattern

### 2.2 Internal Layer Structure

```
┌─────────────────────────────────────────────────┐
│              Servicer Layer (servicers/)          │
│   gRPC entry · Auth · Proto ↔ Domain codec       │
├─────────────────────────────────────────────────┤
│               Logic Layer (logic/)               │
│   Core business logic · frozen dataclass objects │
│   ⛔ Must NOT reference SQLAlchemy Models         │
├─────────────────────────────────────────────────┤
│           Repository Layer (repository/)          │
│   SQLAlchemy 2.0 async mapping · Protocol iface  │
│   Bidirectional Domain Object ↔ Model conversion │
└─────────────────────────────────────────────────┘
```

| Layer | Responsibility | Forbidden |
|-------|---------------|-----------|
| **Servicer** | gRPC entry, auth, proto codec | Business logic |
| **Logic** | Core business logic, state machines | SQLAlchemy Models |
| **Repository** | Async persistence, domain ↔ model conversion | Business logic |

### 2.3 Time & Precision

| Context | Standard |
|---|---|
| **Timezone** | UTC only — naive datetimes forbidden, `timezone=True` required |
| **Precision** | `Numeric`/`Decimal` in DB and Logic — `float` forbidden |
| **Protobuf** | Timestamps as `int64` milliseconds |

### 2.4 Error Handling (`zrun_core.errors`)

> Raising generic exceptions (`Exception`, `ValueError`) is forbidden. Use predefined classes for proper gRPC status mapping.

| Exception | gRPC Status | When to Use |
|-----------|-------------|-------------|
| `ValidationError` | `INVALID_ARGUMENT` | Invalid input format/range |
| `NotFoundError` | `NOT_FOUND` | Resource missing |
| `ConflictError` | `ALREADY_EXISTS` | Uniqueness constraint violated |
| `BusinessError` | `FAILED_PRECONDITION` | Business rule violated |

---

## 3. Code Quality Standards

### 3.1 Dependency Management ⚠️ CRITICAL

**Unified Version Control:** All third-party versions managed in root `pyproject.toml` via `[tool.uv.override-dependencies]`.

**Subproject Standard:** Dependencies in `services/*/` and `shared/*/` must NOT specify versions.

| ✅ Correct | ❌ Incorrect |
|-----------|-------------|
| `"fastapi"` | `"fastapi = "^0.115.0"` |
| `"httpx"` | `"httpx>=0.28.0"` |

**Adding New Dependencies:**
1. Add to root `pyproject.toml` with version
2. Add to subproject `pyproject.toml` without version
3. Run `just init`

### 3.2 SQLAlchemy Best Practices

**Modern declarative syntax only** — `Mapped[T]` and `mapped_column()` required, bare `Column()` forbidden:

```python
# ✅ Correct
class SkuModel(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)

# ❌ Forbidden
class SkuModel(Base):
    id = Column(Integer, primary_key=True)
```

**Protocol interfaces** for dependency inversion:

```python
class SkuRepository(Protocol):
    async def get_by_code(self, session: AsyncSession, code: str) -> SkuDomain: ...
    async def save(self, session: AsyncSession, sku: SkuDomain) -> None: ...
```

### 3.3 Ruff Core Rules

| Rule | Requirement |
|------|------------|
| **EM101/EM102** | Exception messages in variable before constructor: `msg = "error"; raise Error(msg)` |
| **DTZ** | Timezone required for `datetime.now()/utcnow()` — naive datetimes forbidden |
| **TCH** | Type-hint-only imports inside `if TYPE_CHECKING:` block |

---

## 4. Development Workflow

### 4.1 Common Commands

```bash
# Setup
just init           # Initialize workspace and sync dependencies
just proto          # Compile proto files

# Quality Checks
just check          # Full check suite (Format + Lint + Type + Proto)
just format         # Format code
just typecheck      # Type check only

# Services
just list           # List all services
just dev <svc>      # Run service with SQLite (dev mode)
just run <svc>      # Run service with PostgreSQL (production)

# Testing
just test <svc>     # Full test suite
just test-unit <svc>    # Unit tests only
```

### 4.2 Tech Stack

| Category | Technology |
|----------|-----------|
| **Language** | Python 3.14+ (basedpyright standard mode) |
| **Package Manager** | `uv` (workspaces) |
| **Task Runner** | `just` |
| **Communication** | gRPC + asyncio |
| **Persistence** | SQLAlchemy 2.0 Async + asyncpg / aiosqlite |
| **Logging** | structlog |
| **Testing** | pytest + in-memory SQLite |

### 4.3 File Storage

Store temporary working drafts (e.g., `REFACTORING_SUMMARY.md`, `PLAN.md`) in `.ai-drafts/` (excluded from version control).

---

> 📌 **Final note**: When uncertain about a design decision, always prefer the option that makes **complexity converge** over the one with the most features. Maintainability outweighs short-term delivery velocity.
