
# Zrun WMS Development Standards

> This file provides strict architectural guidance for [Claude Code](https://claude.ai/code) when developing **Zrun SaaS WMS** — a production-grade Python monorepo backend. All code contributions must adhere to the service boundaries and quality standards defined in this document.

---

## Table of Contents

1. [Project Vision & Design Philosophy](#1-project-vision--design-philosophy)
2. [Core Tech Stack](#2-core-tech-stack)
3. [Common Development Commands](#3-common-development-commands)
4. [Architectural Standards](#4-architectural-standards)
5. [Code Quality Standards](#5-code-quality-standards)

---

## 1. Project Vision & Design Philosophy

Zrun's core goal is **complexity convergence**. Every code contribution must strictly respect service boundaries to prevent business logic decay.

| Service | Responsibility | Hard Constraints |
|---|---|---|
| **Base** (Static Data) | Core master data & rules (tenants, SKUs, locations) | No inventory handling, no order processing |
| **Stock** (Inventory Core) | Single source of truth for quantities, strong consistency | No business logic, no calls to external systems |
| **Ops** (Operations Hub) | Core business state machines (inbound, outbound, waves, picking) | Must drive Stock — never manipulate quantities directly |
| **Integration** (External Adapter) | Absorbs uncertainty from third-party systems (ERP / 3PL / WCS) | Engineering reliability only — no business logic |
| **Analytics** (Reporting Layer) | Pure read-only layer backed by analytical database | Must not affect live operations or write to the business DB |

---

## 2. Core Tech Stack

| Category | Technology | Notes |
|---|---|---|
| **Language** | Python 3.14+ | Strict type checking, basedpyright standard mode |
| **Package Manager** | `uv` (workspaces) | Dependency isolation across the monorepo |
| **Task Runner** | `just` | Unified command entry point |
| **Communication** | gRPC + asyncio | The only permitted inter-service communication method |
| **Persistence** | SQLAlchemy 2.0 Async API + asyncpg / aiosqlite | asyncpg for production, aiosqlite for dev/test |
| **Logging** | structlog | Structured contextual logging |
| **Testing** | pytest + in-memory SQLite | Fast development validation, no external dependencies |

---

## 3. Common Development Commands

### 3.1 Environment Setup & Proto Compilation

```bash
just init       # Initialize workspace and sync all dependencies
just proto      # Compile Protobuf files (required after any .proto change)
```

### 3.2 Running Services

```bash
just dev <service>    # Start in dev mode with SQLite (e.g. just dev zrun-base)
just run <service>    # Start in production mode with PostgreSQL (requires DATABASE_URL)
just list             # List all macro-services and their current status
```

### 3.3 Quality Checks (run from repo root)

```bash
just check            # Run full check suite (Format + Lint + Type + Proto)
just format-check     # Check code formatting only
just typecheck        # Run basedpyright type checker
```

### 3.4 Testing

```bash
just test <service>               # Run full test suite for a service
just test-unit <service>          # Run unit tests only
just test-integration <service>   # Run integration tests (includes Mock gRPC Context)
```

---

## 4. Architectural Standards

### 4.1 Inter-Service Interaction Rules ⚠️ CRITICAL

> PRs that violate these rules will be rejected without review.

- **No direct imports**: Cross-service `import` is strictly forbidden. For example, `zrun-ops` must never import any module from `zrun-stock`.
- **gRPC is the only interface**: All cross-service calls must go through gRPC interfaces defined in `zrun-schema`.
- **Dependency direction**:
  - `Ops` → `Stock` (synchronous / strongly consistent)
  - `Ops` ↔ `Integration` (command dispatch / event-driven, async permitted)

---

### 4.2 Internal Layer Structure (Layered Architecture)

Every macro-service must strictly follow the three-layer architecture below. **Cross-layer direct references are forbidden.**

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

**Servicer Layer** (`servicers/`)
- Sole gRPC entry point for the service
- Handles authentication (Auth) and authorization checks
- Responsible for bidirectional encoding/decoding between Protobuf messages and domain objects
- Contains no business logic

**Logic Layer** (`logic/`)
- Owns all core business logic and state machines
- Domain objects must be defined with `@dataclass(frozen=True)` to guarantee immutability
- **Strictly forbidden** from referencing any SQLAlchemy Model or ORM-related types

**Repository Layer** (`repository/`)
- Uses SQLAlchemy 2.0 async mapping (`AsyncSession`)
- Must define `Protocol` interfaces for dependency inversion, enabling easy test substitution
- Responsible for bidirectional conversion between Domain Objects and SQLAlchemy Models, fully isolating persistence details

---

### 4.3 Time & Precision Handling

| Context | Standard |
|---|---|
| **Timezone** | Always use UTC. Naive datetimes are forbidden. SQLAlchemy fields must declare `timezone=True` |
| **Quantity Precision** | Use `Numeric` / `Decimal` in the database; use `Decimal` in the Logic layer. **`float` is strictly forbidden** |
| **Protobuf Transport** | Timestamps must be transmitted as `int64` (milliseconds) in Proto definitions |

---

### 4.4 Error Handling (`zrun_core.errors`)

> Raising generic exceptions (e.g. bare `Exception`, `ValueError`) is strictly forbidden. Use predefined exception classes so the Servicer layer can map them to the correct gRPC Status Codes uniformly.

| Exception Class | gRPC Status | When to Use |
|---|---|---|
| `ValidationError` | `INVALID_ARGUMENT` | Input parameter format or range is invalid |
| `NotFoundError` | `NOT_FOUND` | Requested resource does not exist |
| `ConflictError` | `ALREADY_EXISTS` | Resource already exists or uniqueness constraint violated |
| `BusinessError` | `FAILED_PRECONDITION` | Business rule violated (e.g. insufficient stock) |

---

## 5. Code Quality Standards

### 5.1 Ruff Core Rules

| Rule | Requirement |
|---|---|
| **EM101 / EM102** | Exception messages must be assigned to a variable before being passed to the exception constructor. **Correct**: `msg = "Insufficient stock"; raise BusinessError(msg)` |
| **DTZ** | Timezone awareness is enforced. Calls to `datetime.now()` or `datetime.utcnow()` without a `tz` argument are forbidden |
| **TCH** | Imports used only for type hints must be placed inside an `if TYPE_CHECKING:` block to avoid circular imports at runtime |

### 5.2 SQLAlchemy Best Practices

**Use the modern declarative syntax.** All Model fields must use `Mapped[T]` and `mapped_column()`. The legacy bare `Column()` style is forbidden.

```python
# ✅ Correct
class SkuModel(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)

# ❌ Forbidden
class SkuModel(Base):
    id = Column(Integer, primary_key=True)
```

**Manage `AsyncSession` lifecycle explicitly.** Transactions should be opened in the Servicer or Middleware layer. The Repository layer does not own transaction boundaries.

```python
# ✅ Open transactions in the Servicer layer
async with async_session() as session:
    async with session.begin():
        result = await repo.get_sku(session, sku_id)
```

**Define `Protocol` interfaces for dependency inversion** (enables clean test substitution):

```python
from typing import Protocol

class SkuRepository(Protocol):
    async def get_by_code(self, session: AsyncSession, code: str) -> SkuDomain: ...
    async def save(self, session: AsyncSession, sku: SkuDomain) -> None: ...
```

---

> 📌 **Final note**: When uncertain about a design decision, always prefer the option that makes **complexity converge** over the one with the most features. Maintainability in Zrun outweighs short-term delivery velocity.
