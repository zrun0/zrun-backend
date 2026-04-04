"""Performance tests for auth and gRPC client utilities.

These tests measure the performance benefits of:
- JWKS caching
- gRPC connection pooling
- JWT verification efficiency
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zrun_core.auth import (
    JWKSProvider,
    JWKSProviderConfig,
    JWTVerificationConfig,
    verify_jwt_with_jwks,
)
from zrun_core.grpc import GrpcClientManager


@pytest.mark.performance
class TestJWKSCachePerformance:
    """Performance tests for JWKS caching."""

    @pytest.mark.asyncio
    async def test_cache_hit_much_faster_than_fetch(self) -> None:
        """Test that cache hits are significantly faster than network fetches.

        This test verifies that the caching mechanism provides meaningful
        performance improvement by comparing cache hit time vs simulated
        network fetch time.
        """
        config = JWKSProviderConfig(
            jwks_url="https://example.com/jwks.json",
            cache_ttl_seconds=300,
        )
        provider = JWKSProvider(config=config)

        # Mock HTTP client with realistic delay
        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": [{"kty": "RSA", "kid": "key1"}]}
        mock_response.raise_for_status = MagicMock()

        async def mock_get_with_delay(*args: object, **kwargs: object):
            await asyncio.sleep(0.05)  # Simulate 50ms network delay
            return mock_response

        provider._http_client.get = mock_get_with_delay  # type: ignore[method-assign]

        # First call - cache miss, will fetch
        start = time.perf_counter()
        await provider.get_jwks()
        first_call_time = time.perf_counter() - start

        # Second call - cache hit, should be much faster
        start = time.perf_counter()
        await provider.get_jwks()
        second_call_time = time.perf_counter() - start

        # Cache hit should be at least 10x faster than fetch
        # In real scenarios, network latency would be much higher (100-500ms)
        assert second_call_time < first_call_time / 10
        assert second_call_time < 0.01  # Should be sub-millisecond

        await provider.close()

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self) -> None:
        """Test that concurrent access to cache is thread-safe and efficient.

        This test simulates multiple concurrent requests to verify:
        1. Only one network request is made (cache coalescing)
        2. All requests succeed
        3. Total time is close to single request time (not N times)
        """
        mock_response = MagicMock()
        mock_response.json.return_value = {"keys": [{"kty": "RSA", "kid": "key1"}]}
        mock_response.raise_for_status = MagicMock()

        fetch_count = 0

        async def mock_get_with_counter(*args: object, **kwargs: object):
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.01)  # Simulate network delay
            return mock_response

        config = JWKSProviderConfig(
            jwks_url="https://example.com/jwks.json",
            cache_ttl_seconds=300,
        )
        provider = JWKSProvider(config=config)
        provider._http_client.get = mock_get_with_counter  # type: ignore[method-assign]

        # Launch 100 concurrent requests
        tasks = [provider.get_jwks() for _ in range(100)]
        start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start

        # All requests should succeed
        assert len(results) == 100
        assert all("keys" in r for r in results)

        # Only 1-2 network requests should be made (cache coalescing)
        assert fetch_count <= 2

        # Total time should be close to single request time + small overhead
        # With 100 requests and 10ms each, naive would be 1000ms
        # With caching, should be ~10-20ms
        assert total_time < 0.1

        await provider.close()


@pytest.mark.performance
class TestGrpcConnectionPoolPerformance:
    """Performance tests for gRPC connection pooling."""

    @pytest.mark.asyncio
    async def test_connection_reuse_performance(self) -> None:
        """Test that connection reuse is significantly faster than creating new connections.

        This verifies that the connection pool provides meaningful performance
        improvement by reusing existing connections.
        """
        manager = GrpcClientManager()

        # Create first connection
        channel1 = await manager.get_channel("localhost:50051")
        assert channel1 is not None

        # Reuse connection should be faster
        # In real scenario, creating new connection involves DNS + TCP handshake
        start = time.perf_counter()
        for _ in range(100):
            channel = await manager.get_channel("localhost:50051")
            assert channel is channel1  # Should return same object
        reuse_time = time.perf_counter() - start

        # 100 reuses should be very fast (< 1ms)
        assert reuse_time < 0.01

        await manager.close_all()

    @pytest.mark.asyncio
    async def test_pool_efficiency_with_multiple_targets(self) -> None:
        """Test connection pool efficiency with multiple service targets.

        This verifies that the pool correctly manages connections to
        multiple services without creating duplicate connections.
        """
        manager = GrpcClientManager()

        targets = [
            "localhost:50051",
            "localhost:50052",
            "localhost:50053",
        ]

        # Request each target multiple times
        for _ in range(10):
            for target in targets:
                channel = await manager.get_channel(target)
                assert channel is not None

        # Should only have 3 channels in pool (one per target)
        assert len(manager._channels) == 3

        # Each should have ref count of 10
        for target in targets:
            assert manager._ref_counts[target] == 10

        await manager.close_all()


@pytest.mark.performance
class TestJWTVerificationPerformance:
    """Performance tests for JWT verification."""

    @pytest.mark.asyncio
    async def test_verification_performance(self) -> None:
        """Test JWT verification performance is acceptable.

        This test verifies that JWT verification with JWKS lookup
        completes in reasonable time.
        """

        # Mock JWKS provider
        jwks_data = {"keys": [{"kty": "RSA", "kid": "test-key", "n": "test", "e": "AQAB"}]}
        provider = MagicMock(spec=JWKSProvider)
        provider.get_jwks = AsyncMock(return_value=jwks_data)

        config = JWTVerificationConfig(
            audience="test-aud",
            issuer="test-iss",
            algorithms=["RS256"],
        )

        # Mock JWT decode
        with (
            patch("jose.jwt.get_unverified_header", return_value={"kid": "test-key"}),
            patch(
                "jose.jwt.decode",
                return_value={"sub": "user123", "aud": "test-aud", "iss": "test-iss"},
            ),
        ):
            # Measure verification time
            iterations = 100
            start = time.perf_counter()

            for i in range(iterations):
                payload = await verify_jwt_with_jwks(f"token-{i}", provider, config)
                assert payload["sub"] == "user123"

            total_time = time.perf_counter() - start
            avg_time = total_time / iterations

            # Average verification should be fast (< 10ms)
            assert avg_time < 0.01

            # Total for 100 verifications should be reasonable (< 1 second)
            assert total_time < 1.0


@pytest.mark.performance
class TestEndToEndPerformance:
    """End-to-end performance tests for common scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_jwt_verification_speed(self) -> None:
        """Test concurrent JWT verification is fast enough.

        This simulates a realistic scenario where multiple requests come in
        concurrently and each needs JWT verification.
        """

        # Mock JWKS provider
        jwks_data = {"keys": [{"kty": "RSA", "kid": "test-key", "n": "test", "e": "AQAB"}]}
        provider = MagicMock(spec=JWKSProvider)
        provider.get_jwks = AsyncMock(return_value=jwks_data)

        config = JWTVerificationConfig(
            audience="test-aud",
            issuer="test-iss",
        )

        # Mock JWT decode
        with (
            patch("jose.jwt.get_unverified_header", return_value={"kid": "test-key"}),
            patch(
                "jose.jwt.decode",
                return_value={"sub": "user123", "aud": "test-aud", "iss": "test-iss"},
            ),
        ):
            token = "test-token-123"

            # Simulate 100 concurrent requests
            tasks = [verify_jwt_with_jwks(token, provider, config) for _ in range(100)]

            start = time.perf_counter()
            results = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start

            # All requests should succeed
            assert len(results) == 100

            # Should be reasonably fast even without real caching
            # 100 requests in < 1 second is acceptable
            assert total_time < 1.0
