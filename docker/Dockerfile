# =============================================================================
# zrun-backend Service Image
# =============================================================================
# Multi-stage build:
#   - Builder: base + uv (for dependency sync)
#   - Runtime: base only (no uv, smaller image)
#
# Build: docker build --build-arg SERVICE=zrun-base -t zrun-base:latest .
#
# Prerequisites: zrun-base-image:latest must exist (run: just docker-build-base)
# =============================================================================

ARG BASE_IMAGE=zrun-base-image:latest

# =============================================================================
# Builder Stage - Has uv for dependency management
# =============================================================================
FROM ${BASE_IMAGE} AS builder

# Install uv (only in builder stage)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ARG SERVICE

# Copy workspace definition
COPY pyproject.toml uv.lock* ./

# Copy pyproject.toml files for dependency resolution
COPY shared/zrun-core/pyproject.toml shared/zrun-core/
COPY shared/zrun-schema/pyproject.toml shared/zrun-schema/
COPY services/${SERVICE}/pyproject.toml services/${SERVICE}/

# Copy source code
COPY shared/zrun-core/src shared/zrun-core/src
COPY shared/zrun-schema/src shared/zrun-schema/src
COPY services/${SERVICE}/src services/${SERVICE}/src

# Sync only the target package's dependencies
RUN uv sync --frozen --package ${SERVICE}

# =============================================================================
# Runtime Stage - No uv, minimal image
# =============================================================================
FROM ${BASE_IMAGE}

WORKDIR /app

ARG SERVICE
ENV SERVICE_NAME=${SERVICE}

# Copy virtual environment and source code
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/shared /app/shared
COPY --from=builder /app/services /app/services

ENV PATH="/app/.venv/bin:$PATH"

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD grpc_health_probe -addr=:50051 || exit 1

ENTRYPOINT ["sh", "-c", "python -m ${SERVICE_NAME//-/_}.main"]
