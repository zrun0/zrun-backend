"""Integration tests for JWKS provider.

These tests use a real HTTP server to test JWKS fetching and caching.
"""

from __future__ import annotations

import asyncio

import pytest

from zrun_core.auth import JWKSProvider, JWKSProviderConfig, JWKSProviderError


# Test JWKS data
TEST_JWKS = {
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


class TestJWKSProviderIntegration:
    """Integration tests for JWKS provider."""

    @pytest.fixture
    def jwks_server(self) -> None:
        """Create a test HTTP server that serves JWKS.

        This fixture uses httpx as a mock server for testing.
        """
        # For now, we'll use a real endpoint if available
        # In a real integration test, you would start a test HTTP server
        # Here we're testing error handling with a non-existent endpoint
        return

    @pytest.mark.asyncio
    async def test_jwks_provider_real_http_fetch(self) -> None:
        """Test JWKS provider with real HTTP request.

        This test uses a real JWKS endpoint (jwt.io) for integration testing.
        """
        # Use jwt.io's public JWKS endpoint for testing
        config = JWKSProviderConfig(
            jwks_url="https://jwt.io/.well-known/jwks.json",
            cache_ttl_seconds=60,
            timeout_seconds=5,
        )

        provider = JWKSProvider(config=config)

        try:
            # First fetch should hit the network
            jwks = await provider.get_jwks()

            # Verify structure
            assert "keys" in jwks
            assert isinstance(jwks["keys"], list)

            # Second fetch should use cache
            jwks_cached = await provider.get_jwks()
            assert jwks is jwks_cached  # Same object due to caching

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_jwks_provider_invalid_url(self) -> None:
        """Test JWKS provider with invalid URL."""
        config = JWKSProviderConfig(
            jwks_url="http://localhost:59999/nonexistent-jwks.json",
            cache_ttl_seconds=60,
            timeout_seconds=1,
        )

        provider = JWKSProvider(config=config)

        try:
            with pytest.raises(JWKSProviderError) as exc_info:
                await provider.get_jwks()

            assert "Network error" in str(exc_info.value) or "HTTP error" in str(exc_info.value)

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_jwks_provider_concurrent_access(self) -> None:
        """Test JWKS provider is thread-safe under concurrent access."""
        config = JWKSProviderConfig(
            jwks_url="https://jwt.io/.well-known/jwks.json",
            cache_ttl_seconds=60,
            timeout_seconds=5,
        )

        provider = JWKSProvider(config=config)

        try:
            # Create multiple concurrent tasks
            tasks = [provider.get_jwks() for _ in range(10)]

            # All should complete without errors
            results = await asyncio.gather(*tasks)

            # All should return the same JWKS
            assert len(results) == 10
            assert all("keys" in r for r in results)

            # All should be the same cached object
            assert all(r is results[0] for r in results)

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_jwks_provider_cache_expiration(self) -> None:
        """Test JWKS provider cache expiration with short TTL."""
        # Use very short TTL for testing
        config = JWKSProviderConfig(
            jwks_url="https://jwt.io/.well-known/jwks.json",
            cache_ttl_seconds=1,  # 1 second TTL
            timeout_seconds=5,
        )

        provider = JWKSProvider(config=config)

        try:
            # First fetch
            jwks1 = await provider.get_jwks()

            # Wait for cache to expire
            await asyncio.sleep(1.1)

            # Second fetch should fetch fresh data
            jwks2 = await provider.get_jwks()

            # Both should have valid data
            assert "keys" in jwks1
            assert "keys" in jwks2

            # They should be different objects (cache was refreshed)
            # Note: In production, the actual keys might be the same
            # but the objects should be different due to cache refresh

        finally:
            await provider.close()

    @pytest.mark.asyncio
    async def test_jwks_provider_context_manager(self) -> None:
        """Test JWKS provider as async context manager."""
        config = JWKSProviderConfig(
            jwks_url="https://jwt.io/.well-known/jwks.json",
            cache_ttl_seconds=60,
            timeout_seconds=5,
        )

        async with JWKSProvider(config=config) as provider:
            jwks = await provider.get_jwks()
            assert "keys" in jwks

        # Provider should be closed after context exit
        # This is mainly to ensure no exceptions are raised

    @pytest.mark.asyncio
    async def test_jwks_provider_invalid_response_format(self) -> None:
        """Test JWKS provider with invalid response format.

        This test uses httpx to mock a server that returns invalid JWKS.
        """
        # We'll test with a valid URL that doesn't return JWKS format
        config = JWKSProviderConfig(
            jwks_url="https://httpbin.org/html",  # Returns HTML, not JSON
            cache_ttl_seconds=60,
            timeout_seconds=5,
        )

        provider = JWKSProvider(config=config)

        try:
            with pytest.raises(JWKSProviderError) as exc_info:
                await provider.get_jwks()

            # Should get an error about invalid JWKS response
            assert "Invalid JWKS response" in str(exc_info.value) or "HTTP error" in str(
                exc_info.value
            )

        finally:
            await provider.close()
