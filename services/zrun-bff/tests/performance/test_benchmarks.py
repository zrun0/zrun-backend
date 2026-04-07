"""Performance benchmarks for BFF critical paths.

Establishes performance baselines for JWT operations, JWKS fetching,
and gRPC call latency to prevent performance regression.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from zrun_bff.auth.tokens import generate_token_pair
from zrun_bff.config import get_config


@pytest.fixture(scope="session")
def bench_config() -> Generator[None]:
    """Set up test environment for benchmarking."""
    # Generate test RSA key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        private_key_path = Path(tmpdir) / "bench_private.pem"
        private_key_path.write_text(private_pem)

        original_path = os.environ.get("JWT_PRIVATE_KEY_PATH")
        os.environ["JWT_PRIVATE_KEY_PATH"] = str(private_key_path)
        get_config.cache_clear()

        try:
            yield
        finally:
            if original_path:
                os.environ["JWT_PRIVATE_KEY_PATH"] = original_path
            else:
                os.environ.pop("JWT_PRIVATE_KEY_PATH", None)
            get_config.cache_clear()


class TestJWTPairGeneration:
    """Benchmarks for JWT token pair generation."""

    @pytest.mark.benchmark(group="jwt", min_rounds=10)
    def test_generate_token_pair(self, benchmark: object, bench_config: None) -> None:
        """Benchmark token pair generation (access + refresh tokens).

        Target: < 150ms for RS256 token pair generation (2x RSA signatures).
        Note: Ed25519 would be ~0.2ms but requires migration.
        """
        from zrun_bff.config import BFFConfig

        config = BFFConfig()

        def generate_pair() -> None:
            generate_token_pair(
                config=config,
                user_id="benchmark_user",
                scopes="pda:read pda:write",
            )

        benchmark(generate_pair)


class TestGRPCErrorMapping:
    """Benchmarks for gRPC error to HTTP error conversion."""

    @pytest.mark.benchmark(group="error-mapping", min_rounds=100)
    def test_map_grpc_to_http(self, benchmark: object) -> None:
        """Benchmark gRPC to HTTP status code mapping.

        Target: < 0.1ms for status code mapping.
        """
        from grpc import StatusCode
        from zrun_bff.errors import map_grpc_to_http

        benchmark(lambda: map_grpc_to_http(StatusCode.NOT_FOUND))

    @pytest.mark.benchmark(group="error-mapping", min_rounds=100)
    def test_convert_grpc_error_to_bff_error(self, benchmark: object) -> None:
        """Benchmark gRPC error to BFF error conversion.

        Target: < 1ms for error conversion.
        """
        from grpc import StatusCode
        from zrun_bff.errors import grpc_error_to_bff_error

        # Create a mock gRPC error
        class MockRpcError(Exception):
            def __init__(self) -> None:
                self._code = StatusCode.NOT_FOUND
                super().__init__("Resource not found")

            def code(self) -> StatusCode:
                return self._code

            def details(self) -> str:
                return "Resource not found"

        error = MockRpcError()
        benchmark(lambda: grpc_error_to_bff_error(error))


class TestBFFErrorResponse:
    """Benchmarks for BFF error response creation."""

    @pytest.mark.benchmark(group="error-response", min_rounds=100)
    def test_create_error_response_from_bff_error(self, benchmark: object) -> None:
        """Benchmark error response creation from BFF error.

        Target: < 0.5ms for error response creation.
        """
        from zrun_bff.errors import ErrorResponse, NotFoundError

        error = NotFoundError(
            detail="Resource not found",
            context={"resource_type": "SKU", "resource_id": "12345"},
        )

        benchmark(lambda: ErrorResponse.from_bff_error(error))


class TestConfigLoading:
    """Benchmarks for configuration loading."""

    @pytest.mark.benchmark(group="config", min_rounds=100)
    def test_get_config_cached(self, benchmark: object) -> None:
        """Benchmark cached config retrieval.

        Target: < 0.1ms for cached config retrieval.
        """
        # Prime the cache
        get_config()

        benchmark(get_config)
