# zrun-backend

Production-grade Python monorepo for zrun microservices architecture.

## Architecture

This monorepo follows a microservices architecture using gRPC for inter-service communication:

```
zrun-backend/
├── shared/
│   ├── zrun-core/          # Infrastructure library (auth, logging, locking)
│   └── zrun-schema/        # Proto definitions & generated code
├── services/
│   ├── zrun-base/          # Core business service (MVP)
│   ├── zrun-stock/         # Stock management service
│   ├── zrun-ops/           # Operations service
│   ├── zrun-integration/   # Third-party integrations
│   └── zrun-analytics/     # Analytics service
```

## Tech Stack

- **Package Manager**: uv (workspaces mode)
- **Python**: >=3.14
- **Communication**: gRPC with asyncio (`grpc.aio`)
- **Logging**: structlog (JSON format, context-aware for ELK/Loki)
- **Task Automation**: justfile
- **Linting**: ruff
- **Type Checking**: basedpyright (standard mode)
- **Testing**: pytest with pytest-asyncio

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (package manager)
- [just](https://github.com/casey/just) (task runner)
- protoc (protobuf compiler)

### Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install just (macOS)
brew install just

# Initialize workspace
just init
```

### Development

```bash
# Compile proto files
just proto

# Run a service
just run zrun-base

# Run tests
just test zrun-base

# Format code
just format

# Lint code
just lint
```

## Principles

1. **Services never import each other directly** - use gRPC for inter-service communication
2. **Proto files only in `shared/zrun-schema/protos/`** - single source of truth
3. **Shared infrastructure in `zrun-core`** - common utilities for all services
4. **Layered architecture** - Servicer → Logic → Repository
5. **English only** - all code, comments, and documentation

## License

Internal use only.
