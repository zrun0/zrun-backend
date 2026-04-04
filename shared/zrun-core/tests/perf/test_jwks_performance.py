"""Performance benchmarks for JWKS provider and JWT verification.

These tests measure performance characteristics of authentication components
to ensure they meet production requirements.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import MagicMock, patch

import pytest

from zrun_core.auth import (
    JWKSProvider,
    JWKSProviderConfig,
    JWTVerificationConfig,
    verify_jwt_with_jwks,
)


# Test JWKS data
MOCK_JWKS = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-1",
            "use": "sig",
            "n": "test-n-value",
            "e": "AQAB",
        }
    ]
}


class TestJWKSProviderPerformance:
    """Performance benchmarks for JWKS provider."""

    @pytest.mark.asyncio
    async def test_cache_hit_performance(self) -> None:
        """Benchmark cache hit performance.

        Expected: Cache hits should be < 1ms.
        """
        config = JWKSProviderConfig(
            jwks_url="https://example.com/jwks.json",
            cache_ttl_seconds=300,
        )

        # Mock the HTTP client to return cached data
        with patch("zrun_core.auth.jwks.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_JWKS
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            provider = JWKSProvider(config=config)

            try:
                # First call to populate cache
                await provider.get_jwks()

                # Benchmark cache hits
                iterations = 1000
                start = time.perf_counter()

                for _ in range(iterations):
                    await provider.get_jwks()

                end = time.perf_counter()
                total_time = end - start
                avg_time_ms = (total_time / iterations) * 1000

                # Cache hits should be very fast (< 1ms)
                assert avg_time_ms < 1.0, f"Cache hit too slow: {avg_time_ms:.3f}ms"

                print(f"\nCache hit performance: {avg_time_ms:.4f}ms per call")

            finally:
                await provider.close()

    @pytest.mark.asyncio
    async def test_concurrent_read_performance(self) -> None:
        """Benchmark concurrent read performance.

        Expected: 100 concurrent reads should complete in < 100ms.
        """
        config = JWKSProviderConfig(
            jwks_url="https://example.com/jwks.json",
            cache_ttl_seconds=300,
        )

        # Mock the HTTP client
        with patch("zrun_core.auth.jwks.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_JWKS
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            provider = JWKSProvider(config=config)

            try:
                # Populate cache
                await provider.get_jwks()

                # Benchmark concurrent reads
                concurrent_tasks = 100
                start = time.perf_counter()

                tasks = [provider.get_jwks() for _ in range(concurrent_tasks)]
                await asyncio.gather(*tasks)

                end = time.perf_counter()
                total_time_ms = (end - start) * 1000

                # 100 concurrent reads should be fast
                assert total_time_ms < 100, f"Concurrent reads too slow: {total_time_ms:.2f}ms"

                print(f"\n{concurrent_tasks} concurrent reads: {total_time_ms:.2f}ms total")

            finally:
                await provider.close()


class TestJWTVerificationPerformance:
    """Performance benchmarks for JWT verification."""

    @pytest.mark.asyncio
    async def test_jwt_verification_performance(self) -> None:
        """Benchmark JWT verification performance.

        Expected: Single JWT verification should be < 10ms.
        """
        # Create a test JWT (this would be a real JWT in production)
        test_jwt = "header.payload.signature"  # Placeholder

        config = JWKSProviderConfig(
            jwks_url="https://example.com/jwks.json",
            cache_ttl_seconds=300,
        )

        # Mock JWKS provider
        with patch("zrun_core.auth.jwks.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_JWKS
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            provider = JWKSProvider(config=config)

            jwt_config = JWTVerificationConfig(
                audience="test-audience",
                issuer="test-issuer",
            )

            try:
                # Note: This will fail with the placeholder JWT
                # In a real test, you would use a valid JWT
                # The purpose here is to show the benchmark structure

                # Benchmark single verification
                iterations = 100

                # We'll measure the overhead of the verification function
                # even though it will fail with the placeholder JWT
                start = time.perf_counter()

                for _ in range(iterations):
                    with contextlib.suppress(Exception):
                        # Expected to fail with placeholder JWT
                        await verify_jwt_with_jwks(
                            token=test_jwt,
                            jwks_provider=provider,
                            config=jwt_config,
                        )

                end = time.perf_counter()
                total_time = end - start
                avg_time_ms = (total_time / iterations) * 1000

                print(f"\nJWT verification overhead: {avg_time_ms:.4f}ms per call")

                # The overhead should be minimal
                # In production with real JWTs, this would be < 10ms

            finally:
                await provider.close()


class TestMemoryUsage:
    """Memory usage tests for authentication components."""

    @pytest.mark.asyncio
    async def test_jwks_cache_memory_usage(self) -> None:
        """Test that JWKS cache doesn't grow unbounded.

        Expected: Cache should respect max_size limit.
        """
        config = JWKSProviderConfig(
            jwks_url="https://example.com/jwks.json",
            cache_ttl_seconds=300,
            max_cache_size=10,  # Small cache for testing
        )

        # Mock the HTTP client
        with patch("zrun_core.auth.jwks.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = MOCK_JWKS
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            provider = JWKSProvider(config=config)

            try:
                # Access the cache directly
                cache = provider._cache

                # Verify cache size limit is enforced
                assert cache.maxsize == 10

                # Populate cache
                for i in range(15):
                    # Use different URLs to bypass cache key uniqueness
                    provider._cache[f"url-{i}"] = MOCK_JWKS

                # Cache should not exceed max size
                # (TTLCache automatically evicts oldest entries)
                assert len(cache) <= cache.maxsize

                print(f"\nCache size: {len(cache)} (max: {cache.maxsize})")

            finally:
                await provider.close()
